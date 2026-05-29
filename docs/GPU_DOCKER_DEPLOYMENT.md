# GPU Docker Deployment Guide

This document explains how to use a GPU to accelerate `faster-whisper` subtitle generation for a major speed boost.

## Why use GPU acceleration

The only deep-learning step in VideoGenAI is **faster-whisper speech recognition** (turning audio into time-stamped subtitles).

- **CPU mode** (default): subtitle generation with the `large-v3` model is slow.
- **GPU mode**: uses an NVIDIA GPU plus CUDA for a **5-10x speedup**.

> Note: the other stages in the project (script generation, audio synthesis, video editing) do not involve deep learning, so the GPU only accelerates subtitle generation.

## Deployment options

This project ships two Docker deployment options. **The default CPU deployment is not affected in any way.**

### CPU deployment (default, no changes)

```bash
docker compose up -d
```

This uses the original `Dockerfile` (`python:3.11-slim-bullseye`); no GPU is required.

### GPU deployment (for users with an NVIDIA GPU)

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

This uses `Dockerfile.gpu` (`nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04`) and attaches the GPU to the api service.

## Prerequisites for GPU deployment

### 1. Hardware

- An NVIDIA GPU (6 GB of VRAM or more is recommended).
- The `large-v3` model takes about 1.5 GB of VRAM in `float16` precision on the GPU.

### 2. Software

- **NVIDIA driver**: the latest version is fine; confirm with `nvidia-smi`.
- **Docker Desktop**
- **NVIDIA Container Toolkit**: run `docker info` and check whether `nvidia` appears in the list of runtimes.

### 3. Environment check

```bash
# Confirm the NVIDIA driver is working
nvidia-smi

# Confirm Docker supports GPUs (Runtimes should contain nvidia)
docker info | findstr nvidia
```

If there is no `nvidia` runtime, you need to install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) first.

## Configure Whisper to use the GPU

Set the following in `config.toml`:

```toml
subtitle_provider = "whisper"

[whisper]
model_size = "large-v3"
device = "cuda"           # Use the GPU (CPU users should set this to "cpu")
compute_type = "float16"  # float16 is recommended on GPU (CPU users should use "int8")
```

## File overview

| File | Purpose |
|---|---|
| `Dockerfile` | Default CPU image (existing, unchanged) |
| `Dockerfile.gpu` | GPU image (new, based on NVIDIA CUDA) |
| `docker-compose.yml` | Default CPU deployment configuration (existing, unchanged) |
| `docker-compose.gpu.yml` | GPU deployment override configuration (new) |

## GPU deployment steps

### Step 1: Pull the CUDA base image

```bash
docker pull nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
```

> If you use a mirror such as Aliyun, it may return 403 for `nvidia/cuda`. Make sure you can pull directly from Docker Hub.

### Step 2: Update config.toml

Set `subtitle_provider = "whisper"` and `device = "cuda"` as described above.

### Step 3: Build and start

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

### Step 4: Verify the GPU is active

```bash
docker exec -it videogenai-api nvidia-smi
```

If GPU information is shown, the GPU has been attached successfully.

## VRAM and concurrency recommendations

| GPU VRAM | Suggested max concurrent tasks |
|---|---|
| 4 GB | 1-2 |
| 6 GB | 2-3 |
| 8 GB | 3-4 |
| 12 GB or more | 5 |

You can control concurrency through `max_concurrent_tasks` in `config.toml`.

## Troubleshooting

### Issue 1: Image pull fails (403 Forbidden)

The Aliyun mirror returns 403 for `nvidia/cuda`. Workarounds:

- Configure a different working mirror, or
- Pull directly with `docker pull nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04`.

### Issue 2: pip reports `Cannot uninstall blinker`

The `blinker` package shipped with Ubuntu 22.04 is installed through `distutils`, which pip cannot uninstall. `Dockerfile.gpu` already handles this with `apt-get remove -y python3-blinker`.

### Issue 3: `nvidia-smi` inside the container cannot find the GPU

- Confirm the NVIDIA Container Toolkit is installed on the host.
- Confirm that `docker info` lists `nvidia` under Runtimes.
- Confirm you used the GPU deployment command: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`.

### Issue 4: Whisper reports a CUDA error

- Confirm `device = "cuda"` in `config.toml` (case-sensitive, not `"CPU"`).
- Confirm `compute_type = "float16"`.
- Confirm `subtitle_provider = "whisper"`.
