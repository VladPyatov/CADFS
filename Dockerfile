FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    XDG_RUNTIME_DIR=/tmp/xdg-runtime

RUN mkdir -p /tmp/xdg-runtime && chmod 700 /tmp/xdg-runtime

RUN pip uninstall -y cmake

RUN conda install -y -c conda-forge \
        "pythonocc-core=7.9.0" \
        "cmake=3.24" \
    && conda clean -afy

RUN apt-get update \
    && apt-get install --yes \
        git libegl1 libgl1 libgomp1 libgl1-mesa-glx libosmesa6-dev libglu1-mesa-dev \
        pkg-config libxrandr-dev libwayland-dev libxkbcommon-dev libxinerama-dev \
        libxcursor-dev libxi-dev libxext-dev \
    && rm -rf /var/lib/apt/lists/*

# v0.19 release
RUN git clone https://github.com/isl-org/Open3D.git \
    && cd Open3D \
    && git checkout 1e7b174 \
    && mkdir build \
    && cd build \
    && cmake -DENABLE_HEADLESS_RENDERING=ON \
             -DBUILD_GUI=OFF \
             -DUSE_SYSTEM_GLEW=OFF \
             -DUSE_SYSTEM_GLFW=OFF \
             .. \
    && make -j32 \
    && make install-pip-package

RUN git clone https://github.com/hiyouga/LLaMA-Factory.git \
    && cd LLaMA-Factory \
    && git checkout 7af9095 \
    && pip install -e . \
    && pip install -r requirements/metrics.txt

WORKDIR /workspace

# Install pip dependencies (including inference extras)
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[inference]"
RUN pip install --no-cache-dir liger-kernel tensorboardx deepspeed==0.16.4

COPY src/ src/
COPY scripts/ scripts/
COPY configs/ configs/

# data/ and creds/ are expected to be bind-mounted at runtime
VOLUME ["/workspace/data", "/workspace/creds"]
