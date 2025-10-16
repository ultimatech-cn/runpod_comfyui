# --- 1. 基础镜像和环境设置 ---
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ="Etc/UTC"
ENV COMFYUI_PATH=/root/comfy/ComfyUI
ENV VENV_PATH=/venv

# --- 2. 安装系统依赖 ---
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ffmpeg \
    wget \
    unzip \
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# --- 3. 设置 Python 虚拟环境 (VENV) ---
RUN python -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"
RUN /venv/bin/python -m pip install --upgrade pip

# --- 4. 安装 ComfyUI 和核心 Python 包 ---
RUN /venv/bin/python -m pip install comfy-cli
RUN comfy --skip-prompt install --nvidia --cuda-version 12.4

# --- 关键修改：明确安装所有handler需要的依赖 ---
RUN /venv/bin/python -m pip install \
    opencv-python \
    imageio-ffmpeg \
    runpod \
    requests \
    websocket-client

# --- 5. 创建所有模型目录 ---
RUN mkdir -p \
    $COMFYUI_PATH/models/checkpoints \
    $COMFYUI_PATH/models/loras \
    $COMFYUI_PATH/models/controlnet \
    $COMFYUI_PATH/models/upscale_models

# --- 6. 下载所有模型文件 ---
RUN wget -O $COMFYUI_PATH/models/checkpoints/epicrealism_naturalSinRC1VAE.safetensors "https://huggingface.co/dtarnow/epicrealism_naturalSinRC1VAE/resolve/a941b77c791f939be58b4cf8e2bfcbcd6f32c6d6/epicrealism_naturalSinRC1VAE.safetensors"
RUN wget -O $COMFYUI_PATH/models/loras/more_details.safetensors "https://huggingface.co/digiplay/LORA/resolve/main/more_details.safetensors"
RUN wget -O $COMFYUI_PATH/models/loras/SDXLrender_v2.0.safetensors "https://huggingface.co/philz1337x/loras/resolve/main/SDXLrender_v2.0.safetensors"
RUN wget -O $COMFYUI_PATH/models/controlnet/control_v11f1e_sd15_tile.pth "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11f1e_sd15_tile.pth"
RUN wget -O $COMFYUI_PATH/models/upscale_models/4x_foolhardy_Remacri.pth "https://huggingface.co/FacehugmanIII/4x_foolhardy_Remacri/resolve/main/4x_foolhardy_Remacri.pth"
RUN wget -O $COMFYUI_PATH/models/upscale_models/4x_NMKD-Siax_200k.pth "https://huggingface.co/uwg/upscaler/resolve/main/ESRGAN/4x_NMKD-Siax_200k.pth"

# --- 7. 安装所有自定义节点 ---
RUN git clone https://github.com/Extraltodeus/ComfyUI-AutomaticCFG.git $COMFYUI_PATH/custom_nodes/ComfyUI-AutomaticCFG && \
    git clone https://github.com/pamparamm/sd-perturbed-attention.git $COMFYUI_PATH/custom_nodes/sd-perturbed-attention && \
    git clone https://github.com/shiimizu/ComfyUI-TiledDiffusion.git $COMFYUI_PATH/custom_nodes/ComfyUI-TiledDiffusion && \
    git clone https://github.com/EllangoK/ComfyUI-post-processing-nodes.git $COMFYUI_PATH/custom_nodes/ComfyUI-post-processing-nodes

# --- 8. 复制脚本并设置权限 ---
# --- 关键修改：不再复制 workflow_api.json ---
COPY src/start.sh /root/start.sh
COPY src/rp_handler.py /root/rp_handler.py
COPY src/ComfyUI_API_Wrapper.py /root/ComfyUI_API_Wrapper.py

RUN chmod +x /root/start.sh

# --- 9. 定义容器启动命令 ---
CMD ["/root/start.sh"]
