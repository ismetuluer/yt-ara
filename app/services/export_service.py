"""Sonuclari TXT / CSV olarak disa aktarma.

CSV, Turkce Excel ile sorunsuz acilmasi icin BOM'lu UTF-8 ve
noktali virgul ayrac kullanir.
"""
import csv

from app.models.video import VideoResult

CSV_HEADERS = ["Video Başlığı", "Kanal", "Yayın Tarihi", "Video URL"]


def export_txt(path: str, videos: list[VideoResult]) -> int:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for video in videos:
            f.write(video.url + "\n")
    return len(videos)


def export_txt_grouped(path: str, videos: list[VideoResult]) -> int:
    """Videolari kanal adina gore gruplandirip TXT olarak yazar."""
    groups: dict[str, list[VideoResult]] = {}
    for video in videos:
        groups.setdefault(video.channel_title or "Bilinmeyen Kanal", []).append(video)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for channel in sorted(groups):
            group = groups[channel]
            f.write(f"# {channel} ({len(group)})\n")
            for video in group:
                f.write(video.url + "\n")
            f.write("\n")
    return len(videos)


def export_csv(path: str, videos: list[VideoResult]) -> int:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(CSV_HEADERS)
        for video in videos:
            writer.writerow([video.title, video.channel_title,
                             video.published_display, video.url])
    return len(videos)
