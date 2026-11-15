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
