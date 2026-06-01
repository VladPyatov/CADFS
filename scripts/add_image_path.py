import argparse
import json
from pathlib import Path

from tqdm import tqdm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_path', required=True, help='Path to input JSONL file with cad_file_id fields')
    parser.add_argument('--output_path', required=True, help='Path to output JSONL file with images fields added')
    parser.add_argument('--image_dir', required=True, help='Format: image_dir/<id[:4]>/<id>.png or image_dir/<id>.png')
    args = parser.parse_args()

    image_dir = Path(args.image_dir)

    with open(args.input_path) as fin, open(args.output_path, 'w') as fout:
        for line in tqdm(fin):
            obj = json.loads(line)
            cad_id = obj['cad_file_id']
            image_path = image_dir / cad_id[:4] / f'{cad_id}.png'
            if not image_path.exists():
                image_path = image_dir / f'{cad_id}.png'
            if not image_path.exists():
                raise FileNotFoundError(f'Image not found for {cad_id}')
            obj['images'] = [str(image_path)]
            fout.write(json.dumps(obj) + '\n')


if __name__ == '__main__':
    main()
