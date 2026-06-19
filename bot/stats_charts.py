from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def generate_stats_charts(
    daily_activity: list[dict],
    top_surveys: list[dict],
    charts_dir: str = "/tmp/surveybot_charts",
) -> list[Path]:
    output_dir = Path(charts_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    labels = [row["day"] for row in daily_activity]
    new_users_values = [int(row["new_users"]) for row in daily_activity]
    responses_values = [int(row["responses"]) for row in daily_activity]

    chart_paths: list[Path] = []

    bar_path = output_dir / "new_users_30d.png"
    plt.figure(figsize=(12, 4))
    plt.bar(labels, new_users_values, color="#4361ee")
    plt.title("Новые пользователи за последние 30 дней")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(bar_path, dpi=120)
    plt.close()
    chart_paths.append(bar_path)

    line_path = output_dir / "responses_30d.png"
    plt.figure(figsize=(12, 4))
    plt.plot(labels, responses_values, marker="o", color="#2a9d8f")
    plt.title("Прохождения анкет по дням (30 дней)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(line_path, dpi=120)
    plt.close()
    chart_paths.append(line_path)

    pie_path = output_dir / "top5_surveys.png"
    pie_labels = [row["title"] for row in top_surveys[:5]] or ["Нет данных"]
    pie_sizes = [int(row["responses_count"]) for row in top_surveys[:5]] or [1]
    plt.figure(figsize=(7, 7))
    plt.pie(pie_sizes, labels=pie_labels, autopct="%1.1f%%", startangle=140)
    plt.title("Топ-5 анкет по прохождениям")
    plt.tight_layout()
    plt.savefig(pie_path, dpi=120)
    plt.close()
    chart_paths.append(pie_path)

    return chart_paths
