<div align="center">

<p style="font-size:36px;">CADFS: A Big CAD Program Dataset and Framework for Computer-Aided Design with Large Language Models</p>
<div style="display: flex; justify-content: center; gap: 10px;">
  <a href="https://voyleg.github.io/cadfs/" style="display:inline-block;background:#212121;color:white;padding:6px 18px;border-radius:999px;text-decoration:none;font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif;">🚀 Project Page</a>
  <a href="https://huggingface.co/datasets/VladPyatov/CADFS" style="display:inline-block;background:#212121;color:white;padding:6px 18px;border-radius:999px;text-decoration:none;font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif;">🤗 Dataset</a>
  <a href="https://huggingface.co/VladPyatov/CADFS-2B" style="display:inline-block;background:#212121;color:white;padding:6px 18px;border-radius:999px;text-decoration:none;font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif;">🤗 Model</a>
</div>

</div>

<br>


## Contents
1. [Env](#1-env)
2. [Dataset](#2-dataset)
3. [Data processing](#3-data-processing)
4. [Annotations](#4-annotations)
5. [Dataset preparation](#5-dataset-preparation)
6. [Training](#6-training)
7. [Inference](#7-inference)
8. [FeatureScript rendering](#8-featurescript-rendering)
9. [Evaluation](#9-evaluation)
10. [Acknowledgements](#acknowledgements)
11. [Changelog](#changelog)
12. [Citation](#citation)
__________

## 1. Env
<details>
<summary>Option 1. Docker</summary>

```bash
# Build the image
docker build -t cadfs .

# Copy and edit the env file
cp .env.example .env

# Enter the container (CPU)
docker run --rm -it \
  -v "$(pwd)/data:/workspace/data" \
  -v "$(pwd)/creds:/workspace/creds" \
  -v "$(pwd)/models:/workspace/models" \
  --env-file .env \
  cadfs bash

# Enter the container (GPU)
docker run --rm -it --gpus all \
  -v "$(pwd)/data:/workspace/data" \
  -v "$(pwd)/creds:/workspace/creds" \
  -v "$(pwd)/models:/workspace/models" \
  --env-file .env \
  cadfs bash
```

</details>

<details>
<summary>Option 2. Conda</summary>

```bash
conda env create -f environment.yml
conda activate cadfs
# For inference/annotation (vllm + qwen-vl-utils):
# install a CUDA-enabled torch first (CUDA 12.6 wheels shown; pick the index matching your driver)
pip install torch==2.8.0 --extra-index-url https://download.pytorch.org/whl/cu126
pip install ".[inference]"
```
</details>

__________

## 2. Dataset
The dataset is available on [🤗 HuggingFace](https://huggingface.co/datasets/VladPyatov/CADFS/tree/main/cadfs).
To download the whole dataset, run:
```bash
huggingface-cli download VladPyatov/CADFS --repo-type dataset --local-dir ./tmp --include "cadfs/*"
mv ./tmp/cadfs ./data
rm -rf ./tmp
```
`./data` will then contain `dataset/`, `raw/`, `train_data/`, `test_data/`, `misc/` from the HF dataset directly.

To only perform inference or evaluation, download `test_data` and go to [Step 5](#5-dataset-preparation).

__________

## 3. Data processing
To start working with the framework, e.g., to train your models on the dataset, the first step is to obtain the clean FeatureScript representation of CAD models.

<details>
<summary>Option 1. Use the clean FeatureScript from the HF dataset</summary>

```bash
unzip data/dataset/featurescript_rp.zip -d data/dataset
```
This puts the clean FeatureScript programs at `data/dataset/featurescript_rp/{chunk_id:04}/{model_id:08}.txt`,
where `chunk_id` and `model_id` correspond to the chunk and model IDs from the [ABC dataset](https://deep-geometry.github.io/abc-dataset/).
</details>

<details>
<summary>Option 2. Obtain the clean FeatureScript from raw data using our processing pipeline</summary>

Get the raw FeatureScript programs and sketch specification from the HF dataset via
```bash
unzip data/raw/featurescript_raw.zip -d data/raw
unzip data/raw/sketch_raw.zip -d data/raw
```
and run our processing pipeline
```bash
python -m scripts.parse_fscode --fs_dir data/raw/featurescript_raw --sketch_dir data/raw/sketch_raw --output_dir data/dataset/featurescript_rp
```
This saves the clean FeatureScript at `data/dataset/featurescript_rp/{chunk_id:04}/{model_id:08}.txt`,
where `chunk_id` and `model_id` correspond to the chunk and model IDs from the [ABC dataset](https://deep-geometry.github.io/abc-dataset/).
</details>

__________

## 4. Annotations
For text-conditioned generation and image-conditioned reconstruction the essential part is to obtain annotations of CAD models.

<details>
<summary>Option 1. Use the annotations from the HF dataset</summary>

```bash
unzip data/dataset/text_annotations.zip -d data/dataset
unzip data/raw/multiview_images_abc.zip -d data/raw
```
This puts the textual annotations at `data/dataset/text_annotations/{chunk_id:04}/{model_id:08}.txt`,
and the input images for image-conditioned generation at `data/raw/multiview_images_abc/{chunk_id:04}/{model_id:08}.png`.
</details>

<details>
<summary>Option 2. Annotate the FeatureScript programs using our annotation pipeline</summary>

Prepare the clean FeatureScript programs at `data/dataset/featurescript_rp/{chunk_id:04}/{model_id:08}.txt`, as described in Step 3, and run:
```bash
# 1. Copy and edit the env file
cp .env.example .env
# load env vars into the current shell
source .env
# 2. Download the model from HuggingFace into $MODEL_PATH
mkdir -p "$MODEL_PATH"
huggingface-cli download openai/gpt-oss-120b --local-dir "$MODEL_PATH"
# 3. Serve the model with vLLM
vllm serve "$MODEL_PATH" \
    --api-key "$OPENAI_API_KEY" \
    --served-model-name "$OPENAI_MODEL" \
    --tensor-parallel-size 2 \
    --max_model_len 128000 \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.95 \
    --dtype auto \
    --port "$OPENAI_PORT"
# 4. Run annotation pipeline
python -m scripts.annotate --input_dir data/dataset/featurescript_rp --output_dir data/dataset/text_annotations
# 5. Run postprocessing (unicode normalization)
python -m scripts.replace_symbols --input_dir data/dataset/text_annotations
```
This saves the textual annotations at `data/dataset/text_annotations/{chunk_id:04}/{model_id:08}.txt`.

Get the reference CAD models in STL format at `data/raw/stl_abc/{chunk_id:04}/{model_id:08}.stl` via
```bash
unzip data/raw/stl_abc.zip -d data/raw
```
and render the images
```bash
python -m scripts.render_images --input_dir data/raw/stl_abc --output_dir data/raw/multiview_images_abc
```
This saves input images for image-conditioned generation at `data/raw/multiview_images_abc/{chunk_id:04}/{model_id:08}.png`.
</details>

__________

## 5. Dataset preparation
To perform training or inference on the dataset in Steps 6 and 7, prepare the dataset in a specific [JSONL format](https://huggingface.co/datasets/VladPyatov/CADFS#train_data--training-splits).

<details>
<summary>Option 1. Use JSONL files from the HF dataset</summary>

For convenience, we provide JSONL files, obtained by filtering out duplicates and keeping only the samples with input + output fitting within an 8192-token context window.

To prepare data for training, you need
- JSONL files located at `data/train_data/*.jsonl`,
- multi-view images for image-conditioned generation at `data/raw/multiview_images_abc/{chunk_id:04}/{model_id:08}.png`, as described in Step 4.

Then, run
```bash
python -m scripts.add_image_path --input_path data/train_data/stage1_image_train.jsonl --output_path data/train_data/stage1_image_path_train.jsonl --image_dir data/raw/multiview_images_abc
python -m scripts.add_image_path --input_path data/train_data/stage2_image_train.jsonl --output_path data/train_data/stage2_image_path_train.jsonl --image_dir data/raw/multiview_images_abc
```
This adds the paths to the images to the intermediate JSONL files in the `--input_path` and saves the modified JSONL files in the `--output_path`.

To prepare data for testing, first get
- the JSONL file for text-conditioned generation at `data/test_data/CADFS_test/CADFS_text_test.jsonl`,
- and the input images for image-conditioned generation at `data/test_data/CADFS_test/multiview_images_abc/{chunk_id:04}/{model_id:08}.png` via
```bash
unzip data/test_data/CADFS_test.zip -d data/test_data
```

Then, run
```bash
python -m scripts.add_image_path --input_path data/test_data/CADFS_test/CADFS_image_test.jsonl --output_path data/test_data/CADFS_test/CADFS_image_path_test.jsonl --image_dir data/test_data/CADFS_test/multiview_images_abc
```
This adds the paths to the images to the intermediate JSONL file, and saves the modified JSONL file for image-conditioned testing at `data/test_data/CADFS_test/CADFS_image_path_test.jsonl`.
</details>

<details>
<summary>Option 2. Create the JSONL files from scratch</summary>

To prepare data for training, first
- download the data splits at `data/misc/DeepCAD_train_val_test_split.json` and `data/test_data/CADFS_test.json`,
- prepare the clean FeatureScript programs at `data/dataset/featurescript_rp/{chunk_id:04}/{model_id:08}.txt`, as described in Step 3,
- prepare the textual annotations at `data/dataset/text_annotations/{chunk_id:04}/{model_id:08}.txt`
  and the input images at `data/raw/multiview_images_abc/{chunk_id:04}/{model_id:08}.png`, as described in Step 4,
- get the reference CAD models in STL format for extraction of the bounding box information in image-conditioned generation at `data/raw/stl_abc/{chunk_id:04}/{model_id:08}.stl` via
```bash
unzip data/raw/stl_abc.zip -d data/raw
```

Then, run
```bash
# image split (full CADFS dataset, stage 2)
python -m scripts.jsonl_preprocessor \
    --mode image \
    --code_dir data/dataset/featurescript_rp \
    --output_file data/train_data/stage2_image_path_train.jsonl \
    --splits_path data/misc/DeepCAD_train_val_test_split.json \
    --test_path data/test_data/CADFS_test.json \
    --prompts_dir data/raw/multiview_images_abc \
    --stl_dir data/raw/stl_abc
# image split (DeepCAD subset filtering, stage 1)
python -m scripts.filter_jsonl \
    --input_file data/train_data/stage2_image_path_train.jsonl \
    --output_file data/train_data/stage1_image_path_train.jsonl \
    --index data/misc/stage1_indices.json
# text split (full CADFS dataset, stage 2)
python -m scripts.jsonl_preprocessor \
    --mode text \
    --code_dir data/dataset/featurescript_rp \
    --output_file data/train_data/stage2_text_train.jsonl \
    --splits_path data/misc/DeepCAD_train_val_test_split.json \
    --test_path data/test_data/CADFS_test.json \
    --prompts_dir data/dataset/text_annotations
# text split (DeepCAD subset filtering, stage 1)
python -m scripts.filter_jsonl \
    --input_file data/train_data/stage2_text_train.jsonl \
    --output_file data/train_data/stage1_text_train.jsonl \
    --index data/misc/stage1_indices.json
```
This saves the training dataset in JSONL format in `data/train_data`.

Optionally, for the both train stages you can filter out duplicates (similar FeatureScript or B-rep geometry) using `data/misc/unique_models.json` index, for example
```bash
python -m scripts.filter_jsonl --input_file data/train_data/stage1_text_train.jsonl --output_file data/train_data/stage1_text_train_filtered.jsonl --index data/misc/unique_models.json
```

To prepare data for testing on the CADFS test subset, first
- download the data splits at `data/misc/DeepCAD_train_val_test_split.json` and `data/test_data/CADFS_test.json`,
- get the clean FeatureScript programs at `data/test_data/CADFS_test/featurescript_rp/{chunk_id:04}/{model_id:08}.txt`,
- the annotations for text-conditioned generation at `data/test_data/CADFS_test/text_annotations/{chunk_id:04}/{model_id:08}.txt`,
- the input images for image-conditioned generation at `data/test_data/CADFS_test/multiview_images_abc/{chunk_id:04}/{model_id:08}.png`,
- and the reference CAD models in STL format for extraction of the bounding box information in image-conditioned generation at `data/test_data/CADFS_test/stl_abc/{chunk_id:04}/{model_id:08}.stl` via
```bash
unzip data/test_data/CADFS_test.zip -d data/test_data
```

Then, run
```bash
# image split (CADFS)
python -m scripts.jsonl_preprocessor \
    --mode image \
    --code_dir data/test_data/CADFS_test/featurescript_rp \
    --output_file data/test_data/CADFS_image_path_test.jsonl \
    --splits_path data/misc/DeepCAD_train_val_test_split.json \
    --test_path data/test_data/CADFS_test.json \
    --prompts_dir data/test_data/CADFS_test/multiview_images_abc \
    --stl_dir data/test_data/CADFS_test/stl_abc \
    --prepare_test
# text split (CADFS)
    python -m scripts.jsonl_preprocessor \
    --mode text \
    --code_dir data/test_data/CADFS_test/featurescript_rp \
    --output_file data/test_data/CADFS_text_test.jsonl \
    --splits_path data/misc/DeepCAD_train_val_test_split.json \
    --test_path data/test_data/CADFS_test.json \
    --prompts_dir data/test_data/CADFS_test/text_annotations \
    --prepare_test
```
This saves the testing dataset in JSONL format at `data/test_data/CADFS_image_path_test.jsonl` and `data/test_data/CADFS_text_test.jsonl`.

To prepare data for testing on the DeepCAD test subset, first
- download the data splits at `data/misc/DeepCAD_train_val_test_split.json` and `data/test_data/DeepCAD_test.json`,
- get the clean FeatureScript programs at `data/test_data/DeepCAD_test/featurescript_rp/{chunk_id:04}/{model_id:08}.txt`,
- the annotations at `data/test_data/DeepCAD_test/text_annotations/{chunk_id:04}/{model_id:08}.txt`,
- the input images at `data/test_data/DeepCAD_test/multiview_images_abc/{chunk_id:04}/{model_id:08}.png`,
- and the reference STLs at `data/test_data/DeepCAD_test/stl_abc/{chunk_id:04}/{model_id:08}.stl` via
```bash
unzip data/test_data/DeepCAD_test.zip -d data/test_data
```

Then, run
```bash
# image split (DeepCAD)
python -m scripts.jsonl_preprocessor \
    --mode image \
    --code_dir data/test_data/DeepCAD_test/featurescript_rp \
    --output_file data/test_data/DeepCAD_image_path_test.jsonl \
    --splits_path data/misc/DeepCAD_train_val_test_split.json \
    --test_path data/test_data/DeepCAD_test.json \
    --prompts_dir data/test_data/DeepCAD_test/multiview_images_abc \
    --stl_dir data/test_data/DeepCAD_test/stl_abc
    --prepare_test
# text split (DeepCAD)
python -m scripts.jsonl_preprocessor \
    --mode text \
    --code_dir data/test_data/DeepCAD_test/featurescript_rp \
    --output_file data/test_data/DeepCAD_text_test.jsonl \
    --splits_path data/misc/DeepCAD_train_val_test_split.json \
    --test_path data/test_data/DeepCAD_test.json \
    --prompts_dir data/test_data/DeepCAD_test/text_annotations \
    --prepare_test
```
This saves the testing dataset in JSONL format at `data/test_data/DeepCAD_image_path_test.jsonl` and `data/test_data/DeepCAD_text_test.jsonl`.
</details>

__________

## 6. Training
The simplest approach is to use [LLaMA-Factory](https://github.com/hiyouga/LlamaFactory). Please, see the `Dockerfile` for installation details. We provide training and data configs in `configs/`. The training arguments are provided for training with 8 GPUs. You may need to adjust the `gradient_accumulation_steps` and `per_device_train_batch_size` for different setup. If you follow the dataset structure in `./data`, you can just run:
```
cp configs/dataset_info.json .
# run SFT of the Qwen2-VL-2B and save the model in models/CADFS_stage1
FORCE_TORCHRUN=1 llamafactory-cli train configs/CADFS_stage1.yaml
# run SFT of the models/CADFS_stage1 and save the model in models/CADFS_stage2
FORCE_TORCHRUN=1 llamafactory-cli train configs/CADFS_stage2.yaml
```
__________

## 7. Inference
Take the JSONL dataset files `data/test_data/CADFS_test/CADFS_text_test.jsonl`, `data/test_data/CADFS_test/CADFS_image_path_test.jsonl` and the input images for image-conditioned generation, as described in Step 5, and run inference
```bash
# text-conditioned generation
python -m scripts.inference --mode text --checkpoint VladPyatov/CADFS-2B --output_dir data/inference/CADFS_text --split data/test_data/CADFS_test/CADFS_text_test.jsonl
# image-conditioned reconstruction
python -m scripts.inference --mode image --checkpoint VladPyatov/CADFS-2B --output_dir data/inference/CADFS_image --split data/test_data/CADFS_test/CADFS_image_path_test.jsonl
```
This saves the predicted FeatureScript programs at `data/inference/CADFS_text/{model_id:08}.txt` or `data/inference/CADFS_image/{model_id:08}.txt`.

__________

## 8. FeatureScript rendering
To obtain B-reps from the predicted FeatureScript code, create an Onshape account, generate API keys for your team, and put the credentials in `creds/onshape_accounts.json`.
Then take the predicted FeatureScript code from Step 7 at `data/inference/CADFS_text/{model_id:08}.txt`, and run
```bash
python -m scripts.render_featurescript -i data/inference/CADFS_text -o data/inference/CADFS_text_step --rendering -s -1 --workers 4
```
For each program, this saves the respective B-rep in STEP format at `data/inference/CADFS_text_step/{model_id:08}.step`,
or creates `data/inference/CADFS_text_step/{model_id:08}_r.txt` in case of a geometry rendering error,
or creates `data/inference/CADFS_text_step/{model_id:08}_c.txt` in case of a code compilation error.

To only check the FeatureScript code validity, without attempting B-rep geometry export in STEP format, run
```bash
python -m scripts.render_featurescript -i data/inference/CADFS_text -o data/inference/CADFS_text_validation -s -1 --workers 4
```
For each program, this creates `data/inference/CADFS_text_validation/{model_id:08}_ok.txt` for a valid program,
or creates `data/inference/CADFS_text_validation/{model_id:08}_r.txt` in case of a geometry rendering error,
or creates `data/inference/CADFS_text_validation/{model_id:08}_c.txt` in case of a code compilation error.

__________

## 9. Evaluation
To compute 3D reconstruction metrics (CD, NC, ECD) for the obtained B-reps, first
- prepare the predicted B-reps at `data/inference/CADFS_text_step/**/{model_id}.step`, as described in Step 8,
- and get the respective reference at `data/test_data/CADFS_test/step_abc/**/{model_id}.step` via
```bash
unzip data/test_data/CADFS_test.zip -d data/test_data
```
and then, run
```bash
python -m scripts.evaluate_metrics --gt_dir data/test_data/CADFS_test/step_abc --pred_dir data/inference/CADFS_text_step --output_dir data/inference/CADFS_text_metrics --use_safe_workers
```
This compares the predicted B-reps with the reference and saves the values and statistics of the metrics to `metrics_per_shape.csv`, `metrics_summary.json`, `metrics_report.txt` in the `--output_dir`.

__________

## Acknowledgements
We are grateful to Onshape for providing public access to a vast library of CAD designs.

Our code is based on the following awesome repositories:

- [BrepGen](https://github.com/samxuxiang/BrepGen)
- [Cadrille](https://github.com/col14m/cadrille)
- [Onshape API Key](https://github.com/onshape-public/apikey)
- [SECAD-Net](https://github.com/BunnySoCrazy/SECAD-Net/tree/main)

We thank the authors for releasing their code!
__________

## Changelog
#### v1.0, 2026 June 1
- Initial codebase release.
__________

## Citation

If you find our work useful, please cite:

```bibtex
@InProceedings{pyatov2026cadfs,
    author    = {Pyatov, Vladislav and Bobrovskikh, Gleb and Galochkin, Saveliy and Boldyrev, Nikita and Voynov, Oleg and Filippov, Alexander and Ferrer, Gonzalo and Wonka, Peter and Burnaev, Evgeny},
    title     = {CADFS: A Big CAD Program Dataset and Framework for Computer-Aided Design with Large Language Models},
    booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
    month     = {June},
    year      = {2026},
    pages     = {10176-10186}
}
```
