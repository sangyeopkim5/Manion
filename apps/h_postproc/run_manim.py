# manion_postproc/run_manim.py
import subprocess, tempfile, os, shlex

def run_manim_once(code: str, quality="-ql", timeout=30, output_dir=None):
    """
    code: 실행할 manim 코드 (string)
    quality: -ql / -qh 등
    output_dir: 결과 영상이 저장될 디렉토리. None이면 manim 기본 경로 사용.
    """
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "scene.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        # manim CLI command
        cmd = f"manim {quality} {shlex.quote(path)}"
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            cmd += f" -o {shlex.quote(os.path.join(output_dir, 'scene.mp4'))}"

        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        ok = (p.returncode == 0)
        logs = (p.stdout or "") + "\n" + (p.stderr or "")
        return ok, logs
