import subprocess
from pathlib import Path


def render_bibata(svg_repo):

    out = Path("work/bibata_render")
    out.mkdir(parents=True, exist_ok=True)

    subprocess.run(["npm", "run", "build"], cwd=svg_repo)

    return out
