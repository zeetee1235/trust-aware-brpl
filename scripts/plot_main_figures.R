#!/usr/bin/env Rscript

required_packages <- c(
  "ggplot2",
  "dplyr",
  "readr",
  "tidyr",
  "forcats",
  "scales",
  "patchwork"
)

user_lib <- Sys.getenv("R_LIBS_USER", unset = "")
if (identical(user_lib, "")) {
  user_lib <- file.path(Sys.getenv("HOME"), ".local", "share", "R", "site-library")
}
dir.create(user_lib, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(user_lib, .libPaths()))

missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]

if (length(missing_packages) > 0) {
  cat("Using R library:", user_lib, "\n")
  cat("Installing missing R packages:", paste(missing_packages, collapse = ", "), "\n")
  install.packages(missing_packages, repos = "https://cloud.r-project.org", lib = user_lib)
}

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(readr)
  library(tidyr)
  library(forcats)
  library(scales)
  library(patchwork)
})

`%||%` <- function(x, y) if (is.null(x)) y else x

args_all <- commandArgs(trailingOnly = FALSE)
script_flag <- grep("^--file=", args_all, value = TRUE)
script_path <- if (length(script_flag) > 0) {
  normalizePath(sub("^--file=", "", script_flag[1]))
} else {
  normalizePath(file.path(getwd(), "scripts", "plot_main_figures.R"))
}

root_dir <- normalizePath(file.path(dirname(script_path), ".."))
results_dir <- file.path(root_dir, "results")
figures_dir <- file.path(root_dir, "figures")
dir.create(figures_dir, showWarnings = FALSE, recursive = TRUE)

canonical_figures <- c(
  "fig1_pdr_phases.pdf",
  "fig2_resilience_summary.pdf",
  "fig3_attack_tradeoff.pdf",
  "fig4_route_exposure_timeseries.pdf",
  "fig5_trust_trace.pdf",
  "fig6_churn_hotspots.pdf"
)

legacy_figures <- c(
  "fig1_pdr_distribution.pdf",
  "fig1_pdr_phases.pdf",
  "fig2_pdr_timeseries.pdf",
  "fig2_resilience_summary.pdf",
  "fig3_attack_tradeoff.pdf",
  "fig3_delay_cdf.pdf",
  "fig4_route_exposure_timeseries.pdf",
  "fig4_trust_trace.pdf",
  "fig5_parent_churn.pdf",
  "fig5_tabrpl_trust_adversaries.pdf",
  "fig6_churn_hotspots.pdf"
)

unlink(file.path(figures_dir, legacy_figures), force = TRUE)

protocol_levels <- c("RPL", "BRPL", "SMTRUST", "TABRPL")
protocol_colors <- c(
  "RPL" = "#2563eb",
  "BRPL" = "#f97316",
  "SMTRUST" = "#16a34a",
  "TABRPL" = "#dc2626"
)
phase_levels <- c("pre_attack", "during_attack", "recovery")
phase_labels <- c(
  "pre_attack" = "Pre-attack",
  "during_attack" = "During attack",
  "recovery" = "Recovery"
)
phase_colors <- c(
  "pre_attack" = "#94a3b8",
  "during_attack" = "#f97316",
  "recovery" = "#22c55e"
)

save_plot <- function(filename, plot, width = 9, height = 5.5) {
  out <- file.path(figures_dir, filename)
  ggsave(out, plot, width = width, height = height, dpi = 300, device = "pdf")
  message("Saved: ", out)
}

mean_ci_df <- function(x) {
  x <- x[is.finite(x)]
  n <- length(x)
  if (n == 0) {
    return(data.frame(y = NA_real_, ymin = NA_real_, ymax = NA_real_))
  }
  mu <- mean(x)
  se <- if (n > 1) stats::sd(x) / sqrt(n) else 0
  ci <- 1.96 * se
  data.frame(y = mu, ymin = mu - ci, ymax = mu + ci)
}

require_file <- function(name) {
  path <- file.path(results_dir, name)
  if (!file.exists(path)) {
    stop("Missing required input: ", path)
  }
  path
}

theme_main <- function() {
  theme_minimal(base_size = 12) +
    theme(
      plot.background = element_rect(fill = "white", color = NA),
      panel.background = element_rect(fill = "white", color = NA),
      panel.grid.minor = element_blank(),
      panel.grid.major.x = element_blank(),
      panel.grid.major.y = element_line(color = "#e5e7eb", linewidth = 0.35),
      plot.title = element_text(face = "bold", size = 14, margin = margin(b = 4)),
      plot.subtitle = element_text(color = "#374151", size = 10.5, margin = margin(b = 10)),
      plot.title.position = "plot",
      plot.caption.position = "plot",
      axis.title = element_text(face = "bold"),
      axis.text = element_text(color = "#111827"),
      strip.text = element_text(face = "bold", size = 10.5),
      strip.background = element_rect(fill = "#f3f4f6", color = NA),
      legend.position = "top",
      legend.title = element_text(face = "bold"),
      legend.margin = margin(t = 0, r = 0, b = 4, l = 0),
      plot.margin = margin(t = 10, r = 16, b = 12, l = 12)
    )
}

theme_heatmap <- function() {
  theme_main() +
    theme(
      panel.grid = element_blank(),
      axis.text.x = element_text(angle = 0, hjust = 0.5),
      axis.ticks = element_blank()
    )
}

pdr <- read_csv(require_file("pdr_summary.csv"), show_col_types = FALSE) %>%
  mutate(protocol = factor(protocol, levels = protocol_levels))

delay <- read_csv(require_file("delay_summary.csv"), show_col_types = FALSE) %>%
  mutate(protocol = factor(protocol, levels = protocol_levels))

trust <- read_csv(require_file("trust_trace.csv"), show_col_types = FALSE) %>%
  mutate(protocol = factor(protocol, levels = protocol_levels))

churn <- read_csv(require_file("parent_churn.csv"), show_col_types = FALSE) %>%
  mutate(protocol = factor(protocol, levels = protocol_levels))

route <- read_csv(require_file("route_trace.csv"), show_col_types = FALSE) %>%
  mutate(protocol = factor(protocol, levels = protocol_levels))

# ------------------------------------------------------------------
# Figure 1
# Question: Which protocol preserves PDR best across phases?
# ------------------------------------------------------------------
pdr_long <- pdr %>%
  transmute(
    protocol,
    seed,
    pre_attack = pdr_pre_attack * 100,
    during_attack = pdr_during_attack * 100,
    recovery = pdr_recovery * 100
  ) %>%
  pivot_longer(cols = all_of(phase_levels), names_to = "phase", values_to = "pdr") %>%
  mutate(phase = factor(phase, levels = phase_levels, labels = phase_labels))

fig1 <- ggplot(pdr_long, aes(x = protocol, y = pdr, fill = protocol)) +
  geom_violin(width = 0.9, alpha = 0.22, color = NA, trim = FALSE) +
  geom_boxplot(width = 0.22, outlier.shape = NA, alpha = 0.9, linewidth = 0.45) +
  geom_jitter(width = 0.08, alpha = 0.18, size = 1.1, color = "#111827") +
  facet_wrap(~phase, nrow = 1) +
  scale_fill_manual(values = protocol_colors, guide = "none") +
  coord_cartesian(ylim = c(60, 101), clip = "off") +
  labs(
    title = "Fig. 1. Delivery Reliability by Protocol and Phase",
    subtitle = "Violins show the seed distribution; boxplots show median and interquartile range.",
    x = "Protocol",
    y = "PDR (%)"
  ) +
  theme_main()

save_plot("fig1_pdr_phases.pdf", fig1, width = 11.8, height = 5.1)

# ------------------------------------------------------------------
# Figure 2
# Question: How much does each protocol degrade under attack and recover after?
# ------------------------------------------------------------------
resilience <- pdr %>%
  transmute(
    protocol,
    seed,
    attack_drop = (pdr_pre_attack - pdr_during_attack) * 100,
    recovery_gap = (pdr_pre_attack - pdr_recovery) * 100,
    post_attack_gain = (pdr_recovery - pdr_during_attack) * 100
  ) %>%
  pivot_longer(
    cols = c(attack_drop, recovery_gap, post_attack_gain),
    names_to = "metric",
    values_to = "delta"
  ) %>%
  mutate(
    metric = factor(
      metric,
      levels = c("attack_drop", "recovery_gap", "post_attack_gain"),
      labels = c("Drop at attack", "Gap after recovery", "Recovery gain")
    )
  )

fig2 <- ggplot(resilience, aes(x = protocol, y = delta, fill = protocol)) +
  stat_summary(fun = mean, geom = "col", width = 0.64, alpha = 0.9) +
  stat_summary(fun.data = mean_ci_df, geom = "errorbar", width = 0.18, linewidth = 0.5) +
  geom_hline(yintercept = 0, color = "#6b7280", linewidth = 0.4) +
  facet_wrap(~metric, nrow = 1, scales = "free_y") +
  scale_fill_manual(values = protocol_colors, guide = "none") +
  labs(
    title = "Fig. 2. Attack Damage and Recovery by Protocol",
    subtitle = "Bars show the 30-seed mean; whiskers show 95% confidence intervals.",
    x = "Protocol",
    y = "Percentage points"
  ) +
  theme_main()

save_plot("fig2_resilience_summary.pdf", fig2, width = 12.6, height = 5.1)

# ------------------------------------------------------------------
# Figure 3
# Question: What is the reliability-latency trade-off during the attack?
# ------------------------------------------------------------------
tradeoff <- pdr %>%
  transmute(protocol, seed, pdr_attack = pdr_during_attack * 100) %>%
  inner_join(
    delay %>%
      transmute(protocol, seed, delay_attack_ms = delay_during_attack_mean),
    by = c("protocol", "seed")
  ) %>%
  mutate(protocol = factor(protocol, levels = protocol_levels))

tradeoff_summary <- tradeoff %>%
  group_by(protocol) %>%
  summarise(
    pdr_mean = mean(pdr_attack, na.rm = TRUE),
    pdr_sd = sd(pdr_attack, na.rm = TRUE),
    delay_mean = mean(delay_attack_ms, na.rm = TRUE),
    delay_sd = sd(delay_attack_ms, na.rm = TRUE),
    .groups = "drop"
  )

fig3 <- ggplot(tradeoff, aes(x = delay_attack_ms, y = pdr_attack, color = protocol)) +
  geom_point(alpha = 0.28, size = 2.1) +
  geom_point(
    data = tradeoff_summary,
    aes(x = delay_mean, y = pdr_mean, fill = protocol),
    shape = 21, size = 4.8, stroke = 0.9, color = "black", inherit.aes = FALSE
  ) +
  geom_errorbar(
    data = tradeoff_summary,
    aes(x = delay_mean, ymin = pdr_mean - pdr_sd, ymax = pdr_mean + pdr_sd),
    width = 0, linewidth = 0.5, inherit.aes = FALSE
  ) +
  geom_errorbar(
    data = tradeoff_summary,
    aes(y = pdr_mean, xmin = delay_mean - delay_sd, xmax = delay_mean + delay_sd),
    width = 0, linewidth = 0.5, orientation = "y", inherit.aes = FALSE
  ) +
  scale_color_manual(values = protocol_colors) +
  scale_fill_manual(values = protocol_colors, guide = "none") +
  labs(
    title = "Fig. 3. Reliability-Latency Trade-off During the Attack",
    subtitle = "Faint points are seeds; highlighted markers show protocol means with one standard deviation.",
    x = "Mean end-to-end delay during attack (ms)",
    y = "PDR during attack (%)",
    color = "Protocol"
  ) +
  theme_main()

save_plot("fig3_attack_tradeoff.pdf", fig3, width = 9.2, height = 5.8)

# ------------------------------------------------------------------
# Figure 4
# Question: How much do routes remain attached to adversarial parents over time?
# ------------------------------------------------------------------
route_ts <- route %>%
  mutate(
    exposed = if_else(parent_is_sink > 0 | parent_is_attacker > 0, 1, 0),
    time_s = tick / 1000,
    time_bin = floor(time_s / 30) * 30 + 15
  ) %>%
  group_by(protocol, time_bin) %>%
  summarise(
    exposure_pct = mean(exposed, na.rm = TRUE) * 100,
    exposure_lo = quantile(exposed, 0.25, na.rm = TRUE) * 100,
    exposure_hi = quantile(exposed, 0.75, na.rm = TRUE) * 100,
    .groups = "drop"
  )

fig4 <- ggplot(route_ts, aes(x = time_bin, y = exposure_pct, color = protocol, fill = protocol)) +
  geom_ribbon(aes(ymin = exposure_lo, ymax = exposure_hi), alpha = 0.12, color = NA) +
  geom_line(linewidth = 1.1) +
  geom_vline(xintercept = 350, linetype = "dashed", color = "gray40") +
  geom_vline(xintercept = 650, linetype = "dotted", color = "gray40") +
  annotate("rect", xmin = 350, xmax = 650, ymin = -Inf, ymax = Inf, alpha = 0.05, fill = "#ef4444") +
  annotate("label", x = 500, y = max(route_ts$exposure_pct, na.rm = TRUE) * 0.96,
           label = "Attack window", size = 3.1, label.size = 0, fill = alpha("#ffffff", 0.7)) +
  scale_color_manual(values = protocol_colors) +
  scale_fill_manual(values = protocol_colors) +
  labs(
    title = "Fig. 4. Exposure to Adversarial Parents Over Time",
    subtitle = "A node is counted as exposed when its current parent is a sinkhole or blackhole node. Shading shows the interquartile range.",
    x = "Simulation time (s)",
    y = "Nodes currently attached to adversarial parent (%)",
    color = "Protocol",
    fill = "Protocol"
  ) +
  coord_cartesian(xlim = c(0, 930), clip = "off") +
  theme_main()

save_plot("fig4_route_exposure_timeseries.pdf", fig4, width = 10.2, height = 5.8)

# ------------------------------------------------------------------
# Figure 5
# Question: How does TABRPL trust evolve for blackhole and sinkhole neighbors?
# ------------------------------------------------------------------
adv_ids <- c(2, 3, 4, 18)
adv_labels <- c(`2` = "Blackhole 2", `3` = "Blackhole 3", `4` = "Blackhole 4", `18` = "Sinkhole 18")

trust_adv <- trust %>%
  filter(protocol == "TABRPL", nbr_id %in% adv_ids) %>%
  mutate(
    time_s = tick / 1000,
    time_bin = floor(time_s / 30) * 30 + 15,
    nbr_label = factor(as.character(nbr_id), levels = names(adv_labels), labels = adv_labels)
  ) %>%
  group_by(nbr_label, time_bin) %>%
  summarise(
    t_fwd = median(t_fwd, na.rm = TRUE),
    t_ctrl = median(t_ctrl, na.rm = TRUE),
    t_hon = median(t_hon, na.rm = TRUE),
    t_ewma = median(t_ewma, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  pivot_longer(cols = c(t_fwd, t_ctrl, t_hon, t_ewma), names_to = "component", values_to = "value") %>%
  mutate(
    component = factor(component, levels = c("t_fwd", "t_ctrl", "t_hon", "t_ewma"),
                       labels = c("T_fwd", "T_ctrl", "T_hon", "T_EWMA"))
  )

fig5 <- ggplot(trust_adv, aes(x = time_bin, y = value, color = component)) +
  geom_line(linewidth = 1.0) +
  geom_vline(xintercept = 350, linetype = "dashed", color = "gray40") +
  geom_vline(xintercept = 650, linetype = "dotted", color = "gray40") +
  annotate("rect", xmin = 350, xmax = 650, ymin = -Inf, ymax = Inf, alpha = 0.05, fill = "#ef4444") +
  annotate("label", x = 500, y = 980, label = "Attack window", size = 2.9, label.size = 0, fill = alpha("#ffffff", 0.7)) +
  facet_wrap(~nbr_label, ncol = 2, scales = "fixed") +
  scale_color_manual(values = c("T_fwd" = "#2563eb", "T_ctrl" = "#f97316", "T_hon" = "#16a34a", "T_EWMA" = "#dc2626")) +
  labs(
    title = "Fig. 5. TABRPL Trust Dynamics for Adversarial Neighbors",
    subtitle = "Each panel shows the median component trajectory for one adversarial neighbor.",
    x = "Simulation time (s)",
    y = "Trust value (0-1000)",
    color = "Component"
  ) +
  coord_cartesian(xlim = c(0, 930), ylim = c(0, 1000), clip = "off") +
  guides(color = guide_legend(nrow = 1, byrow = TRUE)) +
  theme_main() +
  theme(legend.position = "top")

save_plot("fig5_trust_trace.pdf", fig5, width = 11.2, height = 7.8)

# ------------------------------------------------------------------
# Figure 6
# Question: Where are the routing-instability hotspots?
# ------------------------------------------------------------------
churn_long <- churn %>%
  transmute(
    protocol,
    seed,
    node_id,
    pre_attack = churn_pre_attack,
    during_attack = churn_during_attack,
    recovery = churn_recovery
  ) %>%
  pivot_longer(cols = all_of(phase_levels), names_to = "phase", values_to = "churn")

hot_nodes <- churn_long %>%
  filter(phase == "during_attack") %>%
  group_by(node_id) %>%
  summarise(score = mean(churn, na.rm = TRUE), .groups = "drop") %>%
  arrange(desc(score)) %>%
  slice_head(n = 12) %>%
  pull(node_id)

hotspot_df <- churn_long %>%
  filter(node_id %in% hot_nodes, phase == "during_attack") %>%
  group_by(protocol, node_id) %>%
  summarise(mean_churn = mean(churn, na.rm = TRUE), .groups = "drop") %>%
  mutate(node_id = fct_reorder(factor(node_id), mean_churn, .fun = max, .desc = TRUE))

nonzero_df <- churn_long %>%
  group_by(protocol, phase) %>%
  summarise(nonzero_frac = mean(churn > 0, na.rm = TRUE), .groups = "drop") %>%
  mutate(phase = factor(phase, levels = phase_levels, labels = phase_labels))

heatmap_hotspots <- ggplot(hotspot_df, aes(x = protocol, y = node_id, fill = mean_churn)) +
  geom_tile(color = "white", linewidth = 0.7) +
  geom_text(aes(label = sprintf("%.2f", mean_churn),
                color = mean_churn > median(mean_churn, na.rm = TRUE)),
            size = 3.2, fontface = "bold", show.legend = FALSE) +
  scale_fill_gradient(low = "#fef3c7", high = "#b91c1c") +
  scale_color_manual(values = c("TRUE" = "white", "FALSE" = "#111827")) +
  labs(
    title = "Fig. 6A. During-Attack Churn Hotspots",
    subtitle = "Top 12 nodes ranked by mean during-attack churn.",
    x = "Protocol",
    y = "Node ID",
    fill = "Mean churn"
  ) +
  theme_heatmap()

heatmap_nonzero <- ggplot(nonzero_df, aes(x = protocol, y = phase, fill = nonzero_frac)) +
  geom_tile(color = "white", linewidth = 0.8) +
  geom_text(aes(label = percent(nonzero_frac, accuracy = 0.1),
                color = nonzero_frac > median(nonzero_frac, na.rm = TRUE)),
            size = 3.5, fontface = "bold", show.legend = FALSE) +
  scale_fill_gradient(low = "#e0f2fe", high = "#082f49", labels = percent_format(accuracy = 1)) +
  scale_color_manual(values = c("TRUE" = "white", "FALSE" = "#111827")) +
  labs(
    title = "Fig. 6B. Fraction of Nodes with Any Parent Change",
    subtitle = "This panel shows how widespread churn is, not just how large.",
    x = "Protocol",
    y = "Phase",
    fill = "Node fraction"
  ) +
  theme_heatmap()

fig6 <- heatmap_hotspots + heatmap_nonzero + plot_layout(widths = c(1.45, 1))
save_plot("fig6_churn_hotspots.pdf", fig6, width = 13.2, height = 6.8)

message("All R figures written to: ", figures_dir)
