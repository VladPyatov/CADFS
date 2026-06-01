import argparse
import json
import logging
import multiprocessing
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.logging_config import setup_logging
from src.metrics import utils

setup_logging()
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Evaluate 3D Reconstruction Metrics (CD, NC, ECD)')
    parser.add_argument('--gt_dir', type=str, required=True, help='Directory with Ground Truth files')
    parser.add_argument('--pred_dir', type=str, required=True, help='Directory with Predicted files')
    parser.add_argument('--output_dir', type=str, default='results', help='Directory to save results')
    parser.add_argument('--gt_ext', type=str, default='.step', help='GT file extension (.step, .stl, .ply)')
    parser.add_argument('--pred_ext', type=str, default='.step', help='Prediction file extension')
    parser.add_argument('--num_points', type=int, default=100000, help='Points for CD/NC/ECD')
    parser.add_argument('--workers', type=int, default=multiprocessing.cpu_count(), help='Number of workers')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument(
        '--use_safe_workers',
        action='store_true',
        help='Wrap each task in a separate Process with timeout (slow, but protects from hanging STEP files)',
    )

    args = parser.parse_args()

    utils.set_seed(args.seed)

    pred_dir_name = Path(args.pred_dir).name
    output_subdir = os.path.join(args.output_dir, pred_dir_name)

    if os.path.exists(output_subdir):
        date_str = datetime.now().strftime('%d_%m_%Y_%H_%M')
        output_subdir = os.path.join(args.output_dir, f'{pred_dir_name}_{date_str}')

    os.makedirs(output_subdir, exist_ok=True)
    args.output_dir = output_subdir

    gt_files = utils.find_files(args.gt_dir, args.gt_ext)
    pred_files = utils.find_files(args.pred_dir, args.pred_ext)

    gt_map = {Path(f).stem: f for f in gt_files}
    pred_map = {Path(f).stem: f for f in pred_files}

    common_ids = sorted(list(set(gt_map.keys()) & set(pred_map.keys())))

    logger.info(f'Found {len(gt_files)} GT files and {len(pred_files)} Pred files.')
    logger.info(f'Matching pairs: {len(common_ids)}')

    jobs = [(gt_map[mid], pred_map[mid], args.num_points) for mid in common_ids]

    results_metrics = []

    logger.info(f'Processing {len(jobs)} pairs with {args.workers} workers...')

    pair_fn = utils.process_pair_safe if args.use_safe_workers else utils.process_pair
    pool_cls = utils.NonDaemonPool if args.use_safe_workers else multiprocessing.Pool
    with pool_cls(args.workers) as pool:
        for res in tqdm(pool.imap_unordered(pair_fn, jobs), total=len(jobs)):
            if res is not None:
                results_metrics.append(res)

    df = pd.DataFrame(results_metrics)
    csv_path = os.path.join(args.output_dir, 'metrics_per_shape.csv')
    df.to_csv(csv_path, index=False)

    num_gt_samples = len(gt_files)
    num_successful_pred_samples = len(results_metrics)
    validity_ratio = (num_successful_pred_samples / num_gt_samples * 100) if num_gt_samples > 0 else 0.0
    invalidity_ratio = 100 - validity_ratio

    summary = {
        'count': len(df),
        'Invalidity_ratio': invalidity_ratio,
        'CD_mean': df['CD'].mean() if not df.empty else 0,
        'CD_median': df['CD'].median() if not df.empty else 0,
        'NC_mean': df['NC'].mean() if not df.empty else 0,
        'NC_median': df['NC'].median() if not df.empty else 0,
        'NC_unnorm_mean': df['NC_unnorm'].mean() if not df.empty else 0,
        'NC_unnorm_median': df['NC_unnorm'].median() if not df.empty else 0,
        'ECD_mean': df['ECD'].mean() if not df.empty else 0,
        'ECD_median': df['ECD'].median() if not df.empty else 0,
    }

    summary_str = '\nMetrics Summary:\n' + json.dumps(summary, indent=2)
    logger.info(summary_str)

    summary_path = os.path.join(args.output_dir, 'metrics_summary.json')

    for k, v in summary.items():
        if isinstance(v, (np.floating, float)):
            summary[k] = float(v)
        elif isinstance(v, (np.integer, int)):
            summary[k] = int(v)

    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=4)

    report_path = os.path.join(args.output_dir, 'metrics_report.txt')
    with open(report_path, 'w') as f:
        f.write(summary_str)

    logger.info(f'Saved results to {args.output_dir}')


if __name__ == '__main__':
    main()
