#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(readr)
  library(scales)
  library(tidyr)
})

args <- commandArgs(trailingOnly = TRUE)
out_dir <- if (length(args) >= 1) args[[1]] else "docs/paper/figures/new/main_v2_story"
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

v1 <- read_csv("docs/paper/generated/main_v1_final/summary_by_density.csv", show_col_types = FALSE)
v2 <- read_csv("docs/paper/generated/main_v2_final/summary_by_density.csv", show_col_types = FALSE)
ver <- read_csv("docs/paper/generated/report/version_delta_summary.csv", show_col_types = FALSE)
pair_v2 <- read_csv("docs/paper/generated/main_v2_final/paired_deltas_by_topology.csv", show_col_types = FALSE)

over_v1 <- v1 %>% filter(scope == "overall")
over_v2 <- v2 %>% filter(scope == "overall")

# Helper: save both SVG and PDF
save_dual <- function(plot_obj, base, w = 10, h = 6) {
  grDevices::svg(filename = file.path(out_dir, paste0(base, ".svg")), width = w, height = h)
  print(plot_obj)
  dev.off()
  ggsave(filename = file.path(out_dir, paste0(base, ".pdf")), plot = plot_obj, width = w, height = h, device = cairo_pdf)
}

# Figure 1: v1 vs v2 overall delta comparison
comp <- tibble(
  metric = c("att_share", "hit_ratio", "churn", "PDR_dur"),
  v1 = c(over_v1$delta_att_share_mean, over_v1$delta_hit_ratio_mean, over_v1$delta_churn_mean, over_v1$delta_pdr_dur_mean),
  v2 = c(over_v2$delta_att_share_mean, over_v2$delta_hit_ratio_mean, over_v2$delta_churn_mean, over_v2$delta_pdr_dur_mean)
) %>%
  mutate(direction = if_else(metric %in% c("att_share", "hit_ratio", "churn"), "lower_better", "higher_better")) %>%
  pivot_longer(cols = c(v1, v2), names_to = "version", values_to = "delta")

p1 <- ggplot(comp, aes(x = metric, y = delta, fill = version)) +
  geom_col(position = position_dodge(width = 0.72), width = 0.62) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray45") +
  scale_fill_manual(values = c(v1 = "#a3a3a3", v2 = "#0f766e"), labels = c(v1 = "Main v1", v2 = "Main v2")) +
  labs(title = "Main v1 → Main v2: Overall Delta Shift", x = NULL, y = "Delta (TA-BRPL - BRPL)", fill = NULL) +
  theme_minimal(base_size = 13) +
  theme(plot.title = element_text(face = "bold"), legend.position = "top")
save_dual(p1, "fig_s01_v1_v2_overall_delta", 10, 5.5)

# Figure 2: main v2 density-wise deltas (faceted)
dens <- v2 %>%
  filter(scope %in% c("sparse", "medium", "dense")) %>%
  transmute(
    density = scope,
    att_share = delta_att_share_mean,
    hit_ratio = delta_hit_ratio_mean,
    churn = delta_churn_mean,
    PDR_dur = delta_pdr_dur_mean
  ) %>%
  pivot_longer(cols = -density, names_to = "metric", values_to = "delta")

p2 <- ggplot(dens, aes(x = density, y = delta, fill = density)) +
  geom_col(width = 0.62, show.legend = FALSE) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray45") +
  facet_wrap(~metric, scales = "free_y", ncol = 2) +
  scale_fill_manual(values = c(sparse = "#2563eb", medium = "#0f766e", dense = "#b45309")) +
  labs(title = "Main v2 by Density: Delta Profile", x = NULL, y = "Delta (TA-BRPL - BRPL)") +
  theme_minimal(base_size = 13) +
  theme(plot.title = element_text(face = "bold"), strip.text = element_text(face = "bold"))
save_dual(p2, "fig_s02_v2_density_delta_profile", 10, 7)

# Figure 3: att_share CI forest
forest <- v2 %>%
  filter(scope %in% c("sparse", "medium", "dense", "overall")) %>%
  transmute(
    scope = factor(scope, levels = c("overall", "medium", "sparse", "dense")),
    mean = delta_att_share_mean,
    lo = delta_att_share_ci_lo,
    hi = delta_att_share_ci_hi
  )

p3 <- ggplot(forest, aes(y = scope, x = mean)) +
  geom_vline(xintercept = 0, linetype = "dashed", color = "gray45") +
  geom_errorbarh(aes(xmin = lo, xmax = hi), height = 0.2, color = "#374151") +
  geom_point(size = 3, color = "#0f766e") +
  labs(title = "Attacker-share Reduction with 95% CI (Main v2)", x = "Delta att_share (TA-BRPL - BRPL)", y = NULL) +
  theme_minimal(base_size = 13) +
  theme(plot.title = element_text(face = "bold"))
save_dual(p3, "fig_s03_att_share_forest_ci", 9, 5.5)

# Figure 4: version progression (v1~v13.12)
keep <- c("v1", "v2", "v3", "v4(tj510)", "v5", "v6", "v7", "v8a", "v9", "v10", "v13.8(full40)", "v13.12(full40)")
ver2 <- ver %>%
  filter(label_pretty %in% keep) %>%
  mutate(label_pretty = factor(label_pretty, levels = keep)) %>%
  transmute(
    version = label_pretty,
    att_share = d_att,
    hit_ratio = d_hit,
    churn = d_churn,
    PDR_dur = d_pdr
  ) %>%
  pivot_longer(cols = -version, names_to = "metric", values_to = "delta")

p4 <- ggplot(ver2, aes(x = version, y = delta, group = metric, color = metric)) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray50") +
  geom_line(linewidth = 0.9) +
  geom_point(size = 2) +
  facet_wrap(~metric, scales = "free_y", ncol = 2) +
  scale_color_manual(values = c(att_share = "#0f766e", hit_ratio = "#2563eb", churn = "#dc2626", PDR_dur = "#b45309")) +
  labs(title = "Version-wise Trial-and-Error Trajectory (v1~v13.12)", x = "Version", y = "Delta (TA-BRPL - BRPL)") +
  theme_minimal(base_size = 12) +
  theme(axis.text.x = element_text(angle = 40, hjust = 1), legend.position = "none", plot.title = element_text(face = "bold"), strip.text = element_text(face = "bold"))
save_dual(p4, "fig_s04_version_progression", 12, 7.5)

# Figure 5: Topology-level tradeoff in main v2
pair_plot <- pair_v2 %>%
  transmute(delta_att_share = delta_att_share, delta_churn = delta_churn, density = factor(density, levels = c("sparse", "medium", "dense")))

p5 <- ggplot(pair_plot, aes(x = delta_att_share, y = delta_churn, color = density)) +
  geom_vline(xintercept = 0, linetype = "dashed", color = "gray50") +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray50") +
  geom_point(alpha = 0.7, size = 2.2) +
  scale_color_manual(values = c(sparse = "#2563eb", medium = "#0f766e", dense = "#b45309")) +
  labs(title = "Topology-level Isolation-Cost Tradeoff (Main v2)", x = "Delta att_share (lower is better)", y = "Delta churn (lower is better)", color = "Density") +
  theme_minimal(base_size = 13) +
  theme(plot.title = element_text(face = "bold"), legend.position = "top")
save_dual(p5, "fig_s05_topology_tradeoff", 9, 6)

# Figure 6: pipeline bug fix impact (manual event framing)
bug <- tibble(
  stage = factor(c("Main v1\n(pre-fix)", "Main v2\n(post-fix)"), levels = c("Main v1\n(pre-fix)", "Main v2\n(post-fix)")),
  att_share = c(over_v1$delta_att_share_mean, over_v2$delta_att_share_mean),
  hit_ratio = c(over_v1$delta_hit_ratio_mean, over_v2$delta_hit_ratio_mean),
  pdr_dur = c(over_v1$delta_pdr_dur_mean, over_v2$delta_pdr_dur_mean)
) %>%
  pivot_longer(cols = c(att_share, hit_ratio, pdr_dur), names_to = "metric", values_to = "delta")

p6 <- ggplot(bug, aes(x = stage, y = delta, fill = stage)) +
  geom_col(width = 0.65, show.legend = FALSE) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "gray50") +
  facet_wrap(~metric, scales = "free_y", nrow = 1) +
  scale_fill_manual(values = c("Main v1\n(pre-fix)" = "#a3a3a3", "Main v2\n(post-fix)" = "#0f766e")) +
  labs(title = "Before/After Fix: Direction Flip in Main Results", x = NULL, y = "Delta (TA-BRPL - BRPL)") +
  theme_minimal(base_size = 13) +
  theme(plot.title = element_text(face = "bold"), strip.text = element_text(face = "bold"))
save_dual(p6, "fig_s06_pipeline_fix_impact", 11, 4.5)

cat("[OK] story figures generated to:", out_dir, "\n")
