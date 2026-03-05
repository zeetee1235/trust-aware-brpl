#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(readr)
  library(tidyr)
  library(scales)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  cat("Usage: Rscript scripts/plot_sweep_figures.R <runs_csv> [output_dir]\n")
  quit(status = 1)
}

runs_csv <- args[[1]]
out_dir <- ifelse(length(args) >= 2, args[[2]], "docs/report/sweep")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

if (!file.exists(runs_csv)) {
  stop(paste("runs.csv not found:", runs_csv))
}

df <- read_csv(runs_csv, show_col_types = FALSE)

num_cols <- c("trust_on", "attack_rate", "attack_mode", "sink_delta", "trust_lambda", "trust_gamma",
              "trust_alpha", "e1", "e3", "tx_total", "status")

# Safe numeric conversion for nullable fields
for (col in c("trust_on", "attack_rate", "attack_mode", "sink_delta", "trust_lambda", "trust_gamma",
              "trust_alpha", "e1", "e3", "tx_total")) {
  if (col %in% names(df)) {
    df[[col]] <- suppressWarnings(as.numeric(df[[col]]))
  }
}

df <- df %>%
  mutate(
    status = as.character(status),
    trust_flag = ifelse(trust_on == 1, "Trust ON", "Trust OFF"),
    topo = paste(topology_family, topology_scale, sep = "_")
  )

ok_df <- df %>%
  filter(status == "ok", traffic == "attack", !is.na(e3), !is.na(attack_rate), !is.na(attack_mode))

if (nrow(ok_df) == 0) {
  stop("No valid rows after filtering (status==ok, traffic==attack, non-null e3/attack_rate/attack_mode)")
}

trust_colors <- c("Trust OFF" = "#f97316", "Trust ON" = "#22c55e")

# 1) Trust ON/OFF by attack rate
p1_data <- ok_df %>%
  group_by(attack_rate, trust_flag) %>%
  summarise(mean_e3 = mean(e3, na.rm = TRUE),
            se_e3 = sd(e3, na.rm = TRUE) / sqrt(n()),
            n = n(), .groups = "drop")

p1 <- ggplot(p1_data, aes(x = factor(attack_rate), y = mean_e3, group = trust_flag, color = trust_flag)) +
  geom_line(linewidth = 1.3) +
  geom_point(size = 2.8) +
  geom_errorbar(aes(ymin = mean_e3 - se_e3, ymax = mean_e3 + se_e3), width = 0.15) +
  scale_color_manual(values = trust_colors) +
  labs(title = "Trust ON/OFF vs Attack Rate",
       subtitle = "Metric: e3 (Parent attacker exposure %, lower is better)",
       x = "Attack drop rate (%)", y = "e3 (%)", color = "") +
  theme_minimal(base_size = 12)

ggsave(file.path(out_dir, "fig1_trust_on_off_e3.png"), p1, width = 8.5, height = 5.5, dpi = 300)

# 2) Topology x Attack Mode heatmap (best trust vs notrust delta)
base_notrust <- ok_df %>%
  filter(trust_on == 0) %>%
  group_by(topo, attack_rate, attack_mode) %>%
  summarise(notrust_e3 = mean(e3, na.rm = TRUE), .groups = "drop")

best_trust <- ok_df %>%
  filter(trust_on == 1) %>%
  group_by(topo, attack_rate, attack_mode) %>%
  summarise(best_trust_e3 = min(e3, na.rm = TRUE), .groups = "drop")

p2_data <- inner_join(base_notrust, best_trust, by = c("topo", "attack_rate", "attack_mode")) %>%
  mutate(delta = notrust_e3 - best_trust_e3)

p2 <- ggplot(p2_data, aes(x = factor(attack_mode), y = topo, fill = delta)) +
  geom_tile(color = "white") +
  facet_wrap(~attack_rate, nrow = 1) +
  scale_fill_gradient2(low = "#b91c1c", mid = "#f8fafc", high = "#15803d", midpoint = 0) +
  labs(title = "Topology x Attack Mode: Trust Best Delta",
       subtitle = "delta = e3(notrust mean) - e3(trust best), positive is better",
       x = "Attack mode", y = "Topology", fill = "Delta") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "fig2_topology_mode_delta_heatmap.png"), p2, width = 12, height = 6.5, dpi = 300)

# 3) Lambda x Gamma sweep (trust only)
p3_data <- ok_df %>%
  filter(trust_on == 1, !is.na(trust_lambda), !is.na(trust_gamma)) %>%
  group_by(attack_rate, trust_lambda, trust_gamma) %>%
  summarise(mean_e3 = mean(e3, na.rm = TRUE), n = n(), .groups = "drop")

p3 <- ggplot(p3_data, aes(x = factor(trust_lambda), y = factor(trust_gamma), fill = mean_e3)) +
  geom_tile(color = "white") +
  facet_wrap(~attack_rate, nrow = 1) +
  scale_fill_viridis_c(option = "C", direction = -1) +
  labs(title = "Parameter Sweep: Lambda x Gamma",
       subtitle = "Trust ON only, lower e3 is better",
       x = "lambda", y = "gamma", fill = "Mean e3") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "fig3_lambda_gamma_heatmap.png"), p3, width = 12, height = 5.5, dpi = 300)

# 4) Alpha x Delta sweep (trust only, faceted by attack mode)
p4_data <- ok_df %>%
  filter(trust_on == 1, !is.na(trust_alpha), !is.na(sink_delta)) %>%
  group_by(attack_mode, trust_alpha, sink_delta) %>%
  summarise(mean_e3 = mean(e3, na.rm = TRUE), n = n(), .groups = "drop")

p4 <- ggplot(p4_data, aes(x = factor(trust_alpha), y = factor(sink_delta), fill = mean_e3)) +
  geom_tile(color = "white") +
  facet_wrap(~attack_mode, nrow = 1) +
  scale_fill_viridis_c(option = "C", direction = -1) +
  labs(title = "Parameter Sweep: Alpha x Sink Delta",
       subtitle = "Trust ON only, lower e3 is better",
       x = "alpha", y = "sinkhole delta", fill = "Mean e3") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "fig4_alpha_delta_heatmap.png"), p4, width = 12, height = 5.5, dpi = 300)

# 5) Simulation status by topology
status_df <- df %>%
  mutate(status2 = case_when(
    status == "ok" ~ "ok",
    status == "failed" ~ "failed",
    TRUE ~ "unknown"
  )) %>%
  group_by(topo, status2) %>%
  summarise(n = n(), .groups = "drop")

p5 <- ggplot(status_df, aes(x = reorder(topo, n, sum), y = n, fill = status2)) +
  geom_col(position = "stack") +
  coord_flip() +
  scale_fill_manual(values = c(ok = "#22c55e", failed = "#ef4444", unknown = "#94a3b8")) +
  labs(title = "Simulation Status by Topology",
       x = "Topology", y = "Run count", fill = "") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "fig5_status_by_topology.png"), p5, width = 9, height = 7, dpi = 300)

# Save compact table for quick reporting
summary_tbl <- ok_df %>%
  group_by(topo, attack_rate, attack_mode, trust_flag) %>%
  summarise(
    n = n(),
    mean_e1 = mean(e1, na.rm = TRUE),
    mean_e3 = mean(e3, na.rm = TRUE),
    mean_tx = mean(tx_total, na.rm = TRUE),
    .groups = "drop"
  )

write_csv(summary_tbl, file.path(out_dir, "table_sweep_summary.csv"))

cat("Saved figures and table in:", out_dir, "\n")
cat(" - fig1_trust_on_off_e3.png\n")
cat(" - fig2_topology_mode_delta_heatmap.png\n")
cat(" - fig3_lambda_gamma_heatmap.png\n")
cat(" - fig4_alpha_delta_heatmap.png\n")
cat(" - fig5_status_by_topology.png\n")
cat(" - table_sweep_summary.csv\n")
