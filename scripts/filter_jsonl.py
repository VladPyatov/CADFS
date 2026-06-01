import argparse
import json

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_file', required=True, help='Input jsonl')
    parser.add_argument('--output_file', required=True, help='Output jsonl')
    parser.add_argument('--index', required=True, help='json file with indexes of')
    args = parser.parse_args()

    with open(args.index) as f:
        index = set(json.load(f))

    output = []
    with open(args.input_file) as f:
        for line in f:
            d = json.loads(line)
            if d['cad_file_id'] in index:
                output.append(line)

    with open(args.output_file, 'w') as f:
        f.writelines(output)
