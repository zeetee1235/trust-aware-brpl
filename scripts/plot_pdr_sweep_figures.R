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
  cat("Usage: Rscript scripts/plot_pdr_sweep_figures.R <runs_pdr_csv> [output_dir]\n")
  quit(status = 1)
}

runs_csv <- args[[1]]
out_dir <- ifelse(length(args) >= 2, args[[2]], "docs/report/pdr_sweep")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

if (!file.exists(runs_csv)) {
  stop(paste("runs_pdr.csv not found:", runs_csv))
}

df <- read_csv(runs_csv, show_col_types = FALSE)

for (col in c("trust_on", "attack_rate", "attack_mode", "sink_delta", "trust_lambda", "trust_gamma",
              "trust_alpha", "pdr")) {
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

ok_attack <- df %>%
  filter(status == "ok", traffic == "attack", !is.na(pdr), !is.na(attack_rate), !is.na(attack_mode))

if (nrow(ok_attack) == 0) {
  stop("No valid attack rows with PDR found")
}

trust_colors <- c("Trust OFF" = "#f97316", "Trust ON" = "#22c55e")

# 1) Trust ON/OFF PDR by attack rate
p1_data <- ok_attack %>%
  group_by(attack_rate, trust_flag) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE),
            se_pdr = sd(pdr, na.rm = TRUE) / sqrt(n()),
            n = n(), .groups = "drop")

p1 <- ggplot(p1_data, aes(x = factor(attack_rate), y = mean_pdr, group = trust_flag, color = trust_flag)) +
  geom_line(linewidth = 1.3) +
  geom_point(size = 2.8) +
  geom_errorbar(aes(ymin = mean_pdr - se_pdr, ymax = mean_pdr + se_pdr), width = 0.15) +
  scale_color_manual(values = trust_colors) +
  labs(title = "PDR: Trust ON/OFF vs Attack Rate",
       x = "Attack drop rate (%)", y = "PDR (%)", color = "") +
  theme_minimal(base_size = 12)

ggsave(file.path(out_dir, "pdr_fig1_trust_on_off_by_attack.png"), p1, width = 8.5, height = 5.5, dpi = 300)

# 1b) x=attack_rate, y=PDR by topology (trust ON/OFF)
p1b_data <- ok_attack %>%
  group_by(topo, attack_rate, trust_flag) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop")

p1b <- ggplot(p1b_data, aes(x = attack_rate, y = mean_pdr, color = trust_flag, group = trust_flag)) +
  geom_line(linewidth = 1.0) +
  geom_point(size = 1.8) +
  facet_wrap(~topo, scales = "free_y") +
  scale_color_manual(values = trust_colors) +
  scale_x_continuous(breaks = sort(unique(p1b_data$attack_rate))) +
  labs(title = "PDR vs Attack Rate by Topology",
       x = "Attack drop rate (%)", y = "PDR (%)", color = "") +
  theme_minimal(base_size = 10)

ggsave(file.path(out_dir, "pdr_fig1b_topology_attackrate.png"), p1b, width = 12, height = 8, dpi = 300)

# 1c) x=attack_rate, y=PDR by attack mode (trust ON/OFF)
p1c_data <- ok_attack %>%
  group_by(attack_mode, attack_rate, trust_flag) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop")

p1c <- ggplot(p1c_data, aes(x = attack_rate, y = mean_pdr, color = trust_flag, group = trust_flag)) +
  geom_line(linewidth = 1.1) +
  geom_point(size = 2.0) +
  facet_wrap(~attack_mode, nrow = 1) +
  scale_color_manual(values = trust_colors) +
  scale_x_continuous(breaks = sort(unique(p1c_data$attack_rate))) +
  labs(title = "PDR vs Attack Rate by Attack Mode",
       x = "Attack drop rate (%)", y = "PDR (%)", color = "") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "pdr_fig1c_mode_attackrate.png"), p1c, width = 11, height = 4.8, dpi = 300)

# 1d) x=attack_rate, y=PDR parameter-specific (Trust ON only)
p1d_lambda <- ok_attack %>%
  filter(trust_on == 1, !is.na(trust_lambda)) %>%
  group_by(trust_lambda, attack_rate) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop") %>%
  ggplot(aes(x = attack_rate, y = mean_pdr, color = factor(trust_lambda), group = factor(trust_lambda))) +
  geom_line(linewidth = 1.0) +
  geom_point(size = 1.6) +
  scale_x_continuous(breaks = sort(unique(ok_attack$attack_rate))) +
  labs(title = "PDR vs Attack Rate (Trust ON): Lambda Sweep",
       x = "Attack drop rate (%)", y = "PDR (%)", color = "lambda") +
  theme_minimal(base_size = 10)
ggsave(file.path(out_dir, "pdr_fig1d_lambda_attackrate.png"), p1d_lambda, width = 8.8, height = 5.3, dpi = 300)

p1d_gamma <- ok_attack %>%
  filter(trust_on == 1, !is.na(trust_gamma)) %>%
  group_by(trust_gamma, attack_rate) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop") %>%
  ggplot(aes(x = attack_rate, y = mean_pdr, color = factor(trust_gamma), group = factor(trust_gamma))) +
  geom_line(linewidth = 1.0) +
  geom_point(size = 1.6) +
  scale_x_continuous(breaks = sort(unique(ok_attack$attack_rate))) +
  labs(title = "PDR vs Attack Rate (Trust ON): Gamma Sweep",
       x = "Attack drop rate (%)", y = "PDR (%)", color = "gamma") +
  theme_minimal(base_size = 10)
ggsave(file.path(out_dir, "pdr_fig1e_gamma_attackrate.png"), p1d_gamma, width = 8.8, height = 5.3, dpi = 300)

p1d_alpha <- ok_attack %>%
  filter(trust_on == 1, !is.na(trust_alpha)) %>%
  group_by(trust_alpha, attack_rate) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop") %>%
  ggplot(aes(x = attack_rate, y = mean_pdr, color = factor(trust_alpha), group = factor(trust_alpha))) +
  geom_line(linewidth = 1.0) +
  geom_point(size = 1.6) +
  scale_x_continuous(breaks = sort(unique(ok_attack$attack_rate))) +
  labs(title = "PDR vs Attack Rate (Trust ON): Alpha Sweep",
       x = "Attack drop rate (%)", y = "PDR (%)", color = "alpha") +
  theme_minimal(base_size = 10)
ggsave(file.path(out_dir, "pdr_fig1f_alpha_attackrate.png"), p1d_alpha, width = 8.8, height = 5.3, dpi = 300)

p1d_delta <- ok_attack %>%
  filter(trust_on == 1, !is.na(sink_delta)) %>%
  group_by(sink_delta, attack_rate) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop") %>%
  ggplot(aes(x = attack_rate, y = mean_pdr, color = factor(sink_delta), group = factor(sink_delta))) +
  geom_line(linewidth = 1.0) +
  geom_point(size = 1.6) +
  scale_x_continuous(breaks = sort(unique(ok_attack$attack_rate))) +
  labs(title = "PDR vs Attack Rate (Trust ON): Sinkhole Delta Sweep",
       x = "Attack drop rate (%)", y = "PDR (%)", color = "delta") +
  theme_minimal(base_size = 10)
ggsave(file.path(out_dir, "pdr_fig1g_delta_attackrate.png"), p1d_delta, width = 8.8, height = 5.3, dpi = 300)

# 2) Topology x Attack Mode delta heatmap
base_notrust <- ok_attack %>%
  filter(trust_on == 0) %>%
  group_by(topo, attack_rate, attack_mode) %>%
  summarise(notrust_pdr = mean(pdr, na.rm = TRUE), .groups = "drop")

best_trust <- ok_attack %>%
  filter(trust_on == 1) %>%
  group_by(topo, attack_rate, attack_mode) %>%
  summarise(best_trust_pdr = max(pdr, na.rm = TRUE), .groups = "drop")

p2_data <- inner_join(base_notrust, best_trust, by = c("topo", "attack_rate", "attack_mode")) %>%
  mutate(delta = best_trust_pdr - notrust_pdr)

p2 <- ggplot(p2_data, aes(x = factor(attack_mode), y = topo, fill = delta)) +
  geom_tile(color = "white") +
  facet_wrap(~attack_rate, nrow = 1) +
  scale_fill_gradient2(low = "#b91c1c", mid = "#f8fafc", high = "#15803d", midpoint = 0) +
  labs(title = "PDR Delta Heatmap by Topology and Attack Mode",
       subtitle = "delta = PDR(trust best) - PDR(notrust mean)",
       x = "Attack mode", y = "Topology", fill = "Delta") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "pdr_fig2_topology_mode_delta_heatmap.png"), p2, width = 12, height = 6.5, dpi = 300)

# 3) Lambda sweep
p3 <- ok_attack %>%
  filter(trust_on == 1, !is.na(trust_lambda)) %>%
  group_by(attack_rate, attack_mode, trust_lambda) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop") %>%
  ggplot(aes(x = factor(trust_lambda), y = mean_pdr, group = factor(attack_rate), color = factor(attack_rate))) +
  geom_line() +
  geom_point(size = 2) +
  facet_wrap(~attack_mode, nrow = 1) +
  labs(title = "PDR Sweep: Lambda",
       x = "lambda", y = "Mean PDR (%)", color = "Attack rate") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "pdr_fig3_lambda_sweep.png"), p3, width = 11, height = 5.5, dpi = 300)

# 4) Gamma sweep
p4 <- ok_attack %>%
  filter(trust_on == 1, !is.na(trust_gamma)) %>%
  group_by(attack_rate, attack_mode, trust_gamma) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop") %>%
  ggplot(aes(x = factor(trust_gamma), y = mean_pdr, group = factor(attack_rate), color = factor(attack_rate))) +
  geom_line() +
  geom_point(size = 2) +
  facet_wrap(~attack_mode, nrow = 1) +
  labs(title = "PDR Sweep: Gamma",
       x = "gamma", y = "Mean PDR (%)", color = "Attack rate") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "pdr_fig4_gamma_sweep.png"), p4, width = 11, height = 5.5, dpi = 300)

# 5) Alpha and delta sweeps
p5a <- ok_attack %>%
  filter(trust_on == 1, !is.na(trust_alpha)) %>%
  group_by(attack_rate, attack_mode, trust_alpha) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop") %>%
  ggplot(aes(x = factor(trust_alpha), y = mean_pdr, group = factor(attack_rate), color = factor(attack_rate))) +
  geom_line() + geom_point(size = 2) +
  facet_wrap(~attack_mode, nrow = 1) +
  labs(title = "PDR Sweep: Alpha", x = "alpha", y = "Mean PDR (%)", color = "Attack rate") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "pdr_fig5_alpha_sweep.png"), p5a, width = 11, height = 5.5, dpi = 300)

p5b <- ok_attack %>%
  filter(trust_on == 1, !is.na(sink_delta)) %>%
  group_by(attack_rate, attack_mode, sink_delta) %>%
  summarise(mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop") %>%
  ggplot(aes(x = factor(sink_delta), y = mean_pdr, group = factor(attack_rate), color = factor(attack_rate))) +
  geom_line() + geom_point(size = 2) +
  facet_wrap(~attack_mode, nrow = 1) +
  labs(title = "PDR Sweep: Sinkhole Delta", x = "delta", y = "Mean PDR (%)", color = "Attack rate") +
  theme_minimal(base_size = 11)

ggsave(file.path(out_dir, "pdr_fig6_delta_sweep.png"), p5b, width = 11, height = 5.5, dpi = 300)

summary_tbl <- ok_attack %>%
  group_by(topo, attack_rate, attack_mode, trust_flag, trust_lambda, trust_gamma, trust_alpha, sink_delta) %>%
  summarise(n = n(), mean_pdr = mean(pdr, na.rm = TRUE), .groups = "drop")
write_csv(summary_tbl, file.path(out_dir, "pdr_table_param_summary.csv"))

cat("Saved PDR figures in:", out_dir, "\n")
