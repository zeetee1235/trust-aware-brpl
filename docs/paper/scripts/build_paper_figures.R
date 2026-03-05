#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(readr)
  library(stringr)
  library(tidyr)
  library(purrr)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  cat("Usage: Rscript docs/paper/scripts/build_paper_figures.R <runs_pdr.csv> [output_dir] [cache_csv]\n")
  quit(status = 1)
}

runs_csv <- args[[1]]
out_dir <- ifelse(length(args) >= 2, args[[2]], "docs/paper/figures")
cache_csv <- ifelse(length(args) >= 3, args[[3]], "docs/paper/data/attacker_parent_ratio_cache.csv")
pdr_cache_csv <- "docs/paper/data/pdr_cache.csv"

if (!file.exists(runs_csv)) stop(paste("runs_pdr.csv not found:", runs_csv))
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(dirname(cache_csv), recursive = TRUE, showWarnings = FALSE)

message("Loading: ", runs_csv)
df <- read_csv(runs_csv, show_col_types = FALSE)

parse_run <- function(x) {
  m <- str_match(
    x,
    "^([A-Z]+)_([SML])_(.+?)_p([0-9]+)_mode([0-9]+)(?:_d([0-9]+)_a([0-9.]+)_lam([0-9]+)_gam([0-9]+)_bl([0-9.]+)_blc([0-9.]+))?_s([0-9]+)$"
  )
  tibble(
    topo_family = m[, 2],
    topo_scale = m[, 3],
    scenario = m[, 4],
    attack_rate_name = suppressWarnings(as.numeric(m[, 5])),
    attack_mode_name = suppressWarnings(as.numeric(m[, 6])),
    sink_delta_name = suppressWarnings(as.numeric(m[, 7])),
    trust_alpha_name = suppressWarnings(as.numeric(m[, 8])),
    trust_lambda_name = suppressWarnings(as.numeric(m[, 9])),
    trust_gamma_name = suppressWarnings(as.numeric(m[, 10])),
    bl_thr_name = suppressWarnings(as.numeric(m[, 11])),
    bl_clr_name = suppressWarnings(as.numeric(m[, 12])),
    seed_name = suppressWarnings(as.numeric(m[, 13]))
  )
}

meta <- parse_run(df$run_name)
d <- bind_cols(df, meta) %>%
  mutate(
    pdr = suppressWarnings(as.numeric(pdr)),
    attack_rate = coalesce(suppressWarnings(as.numeric(attack_rate)), attack_rate_name),
    attack_mode = coalesce(suppressWarnings(as.numeric(attack_mode)), attack_mode_name),
    sink_delta = coalesce(suppressWarnings(as.numeric(sink_delta)), sink_delta_name),
    trust_alpha = coalesce(suppressWarnings(as.numeric(trust_alpha)), trust_alpha_name),
    trust_lambda = coalesce(suppressWarnings(as.numeric(trust_lambda)), trust_lambda_name),
    trust_gamma = coalesce(suppressWarnings(as.numeric(trust_gamma)), trust_gamma_name),
    status = as.character(status),
    scenario = str_replace(run_name, "^[A-Z]+_[SML]_", ""),
    scenario = str_replace(scenario, "_p[0-9]+_mode[0-9]+.*$", ""),
    topology = str_to_title(str_to_lower(topo_family)),
    method = case_when(
      str_detect(scenario, "rpl_mrhof") ~ "RPL (MRHOF)",
      str_detect(scenario, "brpl") & str_detect(scenario, "notrust") ~ "BRPL",
      str_detect(scenario, "brpl") & str_detect(scenario, "trust") ~ "TA-BRPL",
      str_detect(scenario, "brpl") ~ "BRPL",
      TRUE ~ "Other"
    ),
    attack_on = if_else(str_detect(scenario, "attack") | attack_rate > 0, TRUE, FALSE)
  )

# Fill missing PDR values by parsing COOJA logs (cached), especially for
# no-attack fairness plot and RPL rows that may be skipped by --only-attack.
parse_pdr_from_log <- function(log_path) {
  if (!file.exists(log_path)) return(NA_real_)
  lines <- readLines(log_path, warn = FALSE)
  tx <- lines[str_detect(lines, "CSV,TX,")]
  rx <- lines[str_detect(lines, "CSV,RX,")]

  if (length(tx) == 0) return(NA_real_)

  tx_keys <- str_match(tx, "CSV,TX,([0-9]+),([0-9]+),")
  tx_keys <- paste(tx_keys[, 2], tx_keys[, 3], sep = "_")
  tx_keys <- tx_keys[!is.na(tx_keys)]

  # CSV,RX,node=1,<src_ip>,<seq>,... or CSV,RX,<src_ip>,<seq>,...
  rx_key1 <- str_match(rx, "CSV,RX,node=1,([^,]+),([0-9]+),")
  rx_key2 <- str_match(rx, "CSV,RX,([^,]+),([0-9]+),")
  src <- ifelse(!is.na(rx_key1[, 2]), rx_key1[, 2], rx_key2[, 2])
  seq <- ifelse(!is.na(rx_key1[, 3]), rx_key1[, 3], rx_key2[, 3])
  rx_keys <- paste(src, seq, sep = "_")
  rx_keys <- rx_keys[!is.na(rx_keys)]

  tx_n <- length(unique(tx_keys))
  rx_n <- length(unique(rx_keys))
  if (tx_n <= 0) return(NA_real_)
  100 * rx_n / tx_n
}

pdr_cache <- tibble(run_name = character(), pdr_calc = numeric())
if (file.exists(pdr_cache_csv)) {
  pdr_cache <- suppressMessages(read_csv(pdr_cache_csv, show_col_types = FALSE))
}

pdr_missing_targets <- d %>%
  filter(is.na(pdr), method != "Other") %>%
  filter((attack_on == FALSE) | (method == "RPL (MRHOF)")) %>%
  select(run_name, run_dir) %>%
  distinct() %>%
  filter(!(run_name %in% pdr_cache$run_name))

if (nrow(pdr_missing_targets) > 0) {
  message("Computing missing PDR from logs for ", nrow(pdr_missing_targets), " runs...")
  new_pdr <- pdr_missing_targets %>%
    mutate(
      pdr_calc = map_dbl(run_dir, ~ parse_pdr_from_log(file.path(.x, "logs", "COOJA.testlog")))
    ) %>%
    select(run_name, pdr_calc)
  pdr_cache <- bind_rows(pdr_cache, new_pdr) %>% distinct(run_name, .keep_all = TRUE)
  write_csv(pdr_cache, pdr_cache_csv)
}

d <- d %>%
  left_join(pdr_cache, by = "run_name") %>%
  mutate(pdr = coalesce(pdr, pdr_calc))

# Keep only valid rows with known method
ok <- d %>% filter(status == "ok", method != "Other")

paper_theme <- theme_minimal(base_size = 14, base_family = "serif") +
  theme(
    plot.title = element_text(face = "bold", size = 18, color = "#0f172a"),
    plot.subtitle = element_text(size = 12, color = "#334155"),
    axis.title = element_text(face = "bold", color = "#0f172a"),
    axis.text = element_text(color = "#1e293b"),
    panel.grid.minor = element_blank(),
    panel.grid.major = element_line(color = "#e2e8f0"),
    legend.title = element_blank(),
    legend.position = "top"
  )

method_cols <- c(
  "RPL (MRHOF)" = "#1d4ed8",
  "BRPL" = "#f97316",
  "TA-BRPL" = "#16a34a"
)

# ---------------- Figure 4: no-attack fairness ----------------
fig4_dat <- ok %>%
  filter(attack_on == FALSE, !is.na(pdr)) %>%
  group_by(topology, method) %>%
  summarise(mean_pdr = mean(pdr), se = sd(pdr) / sqrt(n()), n = n(), .groups = "drop")

p4 <- ggplot(fig4_dat, aes(x = topology, y = mean_pdr, fill = method)) +
  geom_col(position = position_dodge(width = 0.75), width = 0.65, color = "#0f172a", alpha = 0.92) +
  geom_errorbar(
    aes(ymin = mean_pdr - se, ymax = mean_pdr + se),
    width = 0.18,
    position = position_dodge(width = 0.75)
  ) +
  scale_fill_manual(values = method_cols) +
  labs(
    title = "Figure 4. PDR Without Attack",
    subtitle = "Fairness check under normal traffic: performance gap should remain small.",
    x = "Topology",
    y = "PDR (%)"
  ) +
  coord_cartesian(ylim = c(0, 100)) +
  paper_theme

ggsave(file.path(out_dir, "fig4_pdr_no_attack.png"), p4, width = 10, height = 6, dpi = 320)

# ---------------- Figure 5/6/7: PDR vs Attack Rate by topology ----------------
attack_dat <- ok %>%
  filter(attack_on == TRUE, !is.na(pdr), attack_rate > 0) %>%
  group_by(topology, attack_rate, method) %>%
  summarise(mean_pdr = mean(pdr), se = sd(pdr) / sqrt(n()), n = n(), .groups = "drop")

make_topology_plot <- function(topo_name, fig_title, file_name) {
  dd <- attack_dat %>% filter(topology == topo_name)
  p <- ggplot(dd, aes(x = attack_rate, y = mean_pdr, color = method)) +
    geom_line(linewidth = 1.25) +
    geom_point(size = 2.2) +
    geom_ribbon(aes(ymin = mean_pdr - se, ymax = mean_pdr + se, fill = method), alpha = 0.16, color = NA) +
    scale_color_manual(values = method_cols) +
    scale_fill_manual(values = method_cols) +
    scale_x_continuous(breaks = seq(0, 100, 10), limits = c(0, 100)) +
    coord_cartesian(ylim = c(0, 100)) +
    labs(
      title = fig_title,
      subtitle = paste0(topo_name, " topology: robustness under increasing attack intensity"),
      x = "Attack rate (%)",
      y = "PDR (%)"
    ) +
    paper_theme
  ggsave(file.path(out_dir, file_name), p, width = 10, height = 6, dpi = 320)
}

make_topology_plot("Cluster", "Figure 5. PDR vs Attack Rate (Cluster)", "fig5_pdr_vs_attack_cluster.png")
make_topology_plot("Grid", "Figure 6. PDR vs Attack Rate (Grid)", "fig6_pdr_vs_attack_grid.png")
make_topology_plot("Ring", "Figure 7. PDR vs Attack Rate (Ring)", "fig7_pdr_vs_attack_ring.png")

# Additional trust-effect figure (delta)
delta_dat <- attack_dat %>%
  filter(method %in% c("BRPL", "TA-BRPL")) %>%
  select(topology, attack_rate, method, mean_pdr) %>%
  pivot_wider(names_from = method, values_from = mean_pdr)

if (all(c("BRPL", "TA-BRPL") %in% names(delta_dat))) {
  delta_dat <- delta_dat %>% mutate(delta = `TA-BRPL` - BRPL)

  p_delta <- ggplot(delta_dat, aes(x = attack_rate, y = delta, color = topology)) +
    geom_hline(yintercept = 0, color = "#94a3b8", linetype = "dashed") +
    geom_line(linewidth = 1.2) +
    geom_point(size = 2.0) +
    scale_color_manual(values = c("Cluster" = "#0ea5e9", "Grid" = "#8b5cf6", "Ring" = "#f97316")) +
    labs(
      title = "Figure 6-Alt. Trust Effectiveness (ΔPDR)",
      subtitle = "ΔPDR = PDR(TA-BRPL) - PDR(BRPL)",
      x = "Attack rate (%)",
      y = "ΔPDR (%p)"
    ) +
    paper_theme

  ggsave(file.path(out_dir, "fig6_alt_trust_effect_delta.png"), p_delta, width = 10, height = 6, dpi = 320)
}

# ---------------- Figure 8: attacker exposure ----------------
parse_parent_ratio <- function(log_path, attacker_id = 2L) {
  if (!file.exists(log_path)) return(NA_real_)
  lines <- readLines(log_path, warn = FALSE)
  lines <- lines[str_detect(lines, "CSV,PARENT,")]
  if (length(lines) == 0) return(NA_real_)

  parent_ips <- str_split_fixed(str_replace(lines, ".*CSV,PARENT,", ""), ",", 2)[, 2]
  parent_ips <- parent_ips[parent_ips != "none" & parent_ips != "unknown" & nzchar(parent_ips)]
  if (length(parent_ips) == 0) return(NA_real_)

  to_id <- function(ip) {
    if (!str_detect(ip, ":")) return(NA_integer_)
    last <- str_split(ip, ":", simplify = TRUE)
    last <- last[, ncol(last)]
    suppressWarnings(strtoi(last, base = 16L))
  }

  ids <- vapply(parent_ips, to_id, integer(1))
  ids <- ids[!is.na(ids)]
  if (length(ids) == 0) return(NA_real_)
  100 * mean(ids == attacker_id)
}

exp_runs <- ok %>%
  filter(attack_on == TRUE, method %in% c("BRPL", "TA-BRPL"), attack_rate > 0) %>%
  transmute(
    run_name,
    run_dir,
    topology,
    attack_rate,
    method,
    parent_samples = suppressWarnings(as.numeric(parent_samples)),
    parent_attacker_samples = suppressWarnings(as.numeric(parent_attacker_samples)),
    exposure_csv = if_else(!is.na(parent_samples) & parent_samples > 0,
                           100 * parent_attacker_samples / parent_samples,
                           NA_real_)
  )

cache <- tibble(run_name = character(), attacker_parent_ratio = numeric())
if (file.exists(cache_csv)) {
  cache <- suppressMessages(read_csv(cache_csv, show_col_types = FALSE))
}

need <- exp_runs %>% filter(!(run_name %in% cache$run_name))
if (nrow(need) > 0) {
  # Trust-enabled runs usually already have exposure.csv aggregates.
  # Parse logs only for rows that still miss exposure and are not cached.
  need <- need %>% filter(is.na(exposure_csv))
}

if (nrow(need) > 0) {
  message("Computing attacker-parent ratio from logs for ", nrow(need), " runs...")
  new_rows <- need %>%
    mutate(
      attacker_parent_ratio = map_dbl(run_dir, ~ parse_parent_ratio(file.path(.x, "logs", "COOJA.testlog"), attacker_id = 2L))
    ) %>%
    select(run_name, attacker_parent_ratio)
  cache <- bind_rows(cache, new_rows) %>% distinct(run_name, .keep_all = TRUE)
  write_csv(cache, cache_csv)
}

exp_dat <- exp_runs %>%
  left_join(cache, by = "run_name") %>%
  mutate(exposure = coalesce(exposure_csv, attacker_parent_ratio)) %>%
  filter(!is.na(exposure)) %>%
  group_by(topology, attack_rate, method) %>%
  summarise(mean_exposure = mean(exposure), se = sd(exposure) / sqrt(n()), n = n(), .groups = "drop")

p8 <- ggplot(exp_dat, aes(x = attack_rate, y = mean_exposure, color = method)) +
  geom_line(linewidth = 1.2) +
  geom_point(size = 2.0) +
  geom_ribbon(aes(ymin = pmax(0, mean_exposure - se), ymax = mean_exposure + se, fill = method), alpha = 0.16, color = NA) +
  facet_wrap(~topology, nrow = 1) +
  scale_color_manual(values = method_cols[c("BRPL", "TA-BRPL")]) +
  scale_fill_manual(values = method_cols[c("BRPL", "TA-BRPL")]) +
  labs(
    title = "Figure 8. Attacker Exposure",
    subtitle = "% nodes using attacker as parent (BRPL trust-off vs TA-BRPL trust-on)",
    x = "Attack rate (%)",
    y = "Attacker parent usage (%)"
  ) +
  paper_theme

ggsave(file.path(out_dir, "fig8_attacker_exposure.png"), p8, width = 12, height = 5.6, dpi = 320)

# ---------------- Optional: Trust/Blacklist dynamics ----------------
cand <- ok %>%
  filter(method == "TA-BRPL", attack_on == TRUE, !is.na(attack_rate)) %>%
  mutate(
    target = abs(attack_rate - 50) + if_else(topology == "Cluster" & topo_scale == "M", 0, 100)
  ) %>%
  arrange(target)

if (nrow(cand) > 0) {
  run <- cand$run_dir[[1]]
  run_name <- cand$run_name[[1]]
  thr <- coalesce(cand$bl_thr_name[[1]], 0.90)
  tm <- file.path(run, "trust_metrics.csv")

  if (file.exists(tm)) {
    tdf <- suppressMessages(read_csv(tm, show_col_types = FALSE)) %>%
      mutate(t = row_number(), ewma = suppressWarnings(as.numeric(ewma))) %>%
      filter(!is.na(ewma))

    if (nrow(tdf) > 0) {
      tdf <- tdf %>% mutate(blacklist_state = ewma < thr)

      p_opt <- ggplot(tdf, aes(x = t, y = ewma)) +
        geom_line(color = "#0f766e", linewidth = 1.1) +
        geom_hline(yintercept = thr, color = "#ef4444", linetype = "dashed", linewidth = 1) +
        geom_point(data = tdf %>% filter(blacklist_state), aes(x = t, y = ewma), color = "#dc2626", size = 1.2, alpha = 0.8) +
        annotate("label", x = max(tdf$t) * 0.78, y = thr + 0.04,
                 label = paste0("Blacklist threshold = ", sprintf("%.2f", thr)),
                 size = 4, fill = "#fee2e2", color = "#7f1d1d") +
        labs(
          title = "Figure 8-Alt. Trust / Blacklist Dynamics",
          subtitle = paste0("Representative run: ", run_name),
          x = "Observation step",
          y = "Trust score (EWMA, 0..1)"
        ) +
        paper_theme

      ggsave(file.path(out_dir, "fig8_alt_trust_blacklist_dynamics.png"), p_opt, width = 11, height = 5.6, dpi = 320)
    }
  }
}

# Optional parent switching stability
ps <- ok %>%
  filter(attack_on == TRUE, method %in% c("BRPL", "TA-BRPL"), attack_rate > 0) %>%
  mutate(parent_switch_rate = suppressWarnings(as.numeric(parent_samples)))

# Summary table for manuscript
summary_tbl <- attack_dat %>%
  select(topology, attack_rate, method, mean_pdr, se, n) %>%
  arrange(topology, attack_rate, method)

write_csv(summary_tbl, file.path(out_dir, "table_attack_pdr_summary.csv"))

message("Saved paper figures to: ", out_dir)
