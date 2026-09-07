"""Alt surec yardimcilari."""
import os
import subprocess


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Bir sureci alt surecleriyle birlikte durdurur.

    Bazi araclar (yt-dlp.exe gibi) alt surecler baslatabilir; yalnizca ana
    sureci oldurmek pipe'lari acik birakip iptal sonrasi `communicate()`'in
    beklemeye devam etmesine yol acabilir. Windows'ta tum surec agacini
    kapatir.
    """
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            proc.kill()
    except OSError:
        pass
