"""Execute untrusted Python in a fresh offline Linux container."""
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


async def evaluate_code(source, transcripts):
    image = os.environ.get("EVALSCOUT_GRADER_IMAGE", "python:3.12-slim")
    name = "evalscout-grade-" + uuid4().hex
    with TemporaryDirectory(prefix="evalscout-grade-") as work:
        file = Path(work, "evaluator.py")
        file.write_bytes(source)
        file.chmod(0o444)
        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm", "--pull", "never", "--name", name, "--network", "none",
            "--read-only", "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt",
            "no-new-privileges", "--memory", "256m", "--cpus", "1", "--pids-limit", "32",
            "--log-driver", "none", "-i", "-v", f"{file}:/evaluator.py:ro", image,
            "python3", "-IB", "/evaluator.py",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        async def send():
            proc.stdin.write(transcripts)
            await proc.stdin.drain()
            proc.stdin.close()

        async def collect():
            sender = asyncio.create_task(send())
            result = bytearray()
            try:
                while chunk := await proc.stdout.read(65536):
                    result.extend(chunk)
                    if len(result) > 512_000:
                        raise ValueError("Evaluator output limit exceeded")
                await sender
                if await proc.wait():
                    raise ValueError("Evaluator returned a nonzero exit status")
                return bytes(result)
            finally:
                if not sender.done():
                    sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)

        try:
            return await asyncio.wait_for(collect(), 35)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
                cleanup = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", name, stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await cleanup.wait()


async def evaluate_on_modal(source, transcripts):
    """Use a fresh Modal Sandbox. No app mounts or secrets enter it."""
    import modal
    from modal.stream_type import StreamType

    loader = """
import os, resource, sys, tempfile
size = int(sys.stdin.buffer.readline())
if not 0 < size <= 100000:
    raise SystemExit(2)
source = sys.stdin.buffer.read(size)
transcripts = sys.stdin.buffer.read()
with tempfile.TemporaryDirectory() as directory:
    path = directory + '/evaluator.py'
    with open(path, 'wb') as f:
        f.write(source)
    with open(directory + '/input', 'w+b') as data:
        data.write(transcripts)
        data.seek(0)
        os.dup2(data.fileno(), 0)
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (524288, 524288))
        os.chdir(directory)
        os.execve(sys.executable, [sys.executable, '-IB', path], {'LANG': 'C.UTF-8'})
"""

    async def run():
        app = await modal.App.lookup.aio("evalscout-benchmark")
        sandbox = await modal.Sandbox.create.aio(
            app=app, image=modal.Image.debian_slim(python_version="3.12"),
            block_network=True, timeout=90, cpu=1, memory=256,
        )
        try:
            proc = await sandbox.exec.aio(
                "python", "-IB", "-c", loader, text=False, timeout=35,
                stderr=StreamType.DEVNULL,
            )
            proc.stdin.write(str(len(source)).encode() + b"\n" + source + transcripts)
            proc.stdin.write_eof()
            await proc.stdin.drain.aio()
            output = bytearray()
            async for chunk in proc.stdout:
                output.extend(chunk)
                if len(output) > 512_000:
                    raise ValueError("Evaluator output limit exceeded")
            code = await proc.wait.aio()
            if code:
                raise ValueError("Evaluator returned a nonzero exit status")
            return bytes(output)
        finally:
            await sandbox.terminate.aio()

    return await asyncio.wait_for(run(), 80)
