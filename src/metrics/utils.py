import logging
import os
import queue
import random
import tempfile
from multiprocessing import Process, Queue
from multiprocessing.pool import Pool
from pathlib import Path

import numpy as np
import trimesh
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.StlAPI import StlAPI_Writer
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Random Seed
# -----------------------------------------------------------------------------


def set_seed(seed):
    """Set random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)


# -----------------------------------------------------------------------------
# File Loading and Sampling
# -----------------------------------------------------------------------------


def step_to_points(step_file: str, num_points: int = 10000):
    """Convert a STEP file to points and normals via temporary STL."""
    if STEPControl_Reader is None:
        raise ImportError('OCC (pythonocc-core) is required for STEP files.')

    step_reader = STEPControl_Reader()
    status = step_reader.ReadFile(step_file)
    if status != IFSelect_RetDone:
        raise RuntimeError(f'Error reading STEP file: {step_file}')

    step_reader.TransferRoots()
    shape = step_reader.OneShape()

    mesh = BRepMesh_IncrementalMesh(shape, 0.1)
    mesh.Perform()

    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmp:
        stl_writer = StlAPI_Writer()
        stl_writer.Write(shape, tmp.name)
        tmp_path = tmp.name

    try:
        points, normals = stl_to_points(tmp_path, num_points)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return points, normals


def stl_to_points(stl_file: str, num_points: int = 10000):
    """Convert a STL file to points and normals using trimesh."""
    if trimesh is None:
        raise ImportError('trimesh is required for mesh processing.')

    mesh = trimesh.load(stl_file)
    points, face_indices = mesh.sample(num_points, return_index=True)
    normals = mesh.face_normals[face_indices]

    return points, normals


def obj_to_points(obj_file: str, num_points: int = 10000):
    """Convert a OBJ file to points and normals."""
    if trimesh is None:
        raise ImportError('trimesh is required for mesh processing.')

    mesh = trimesh.load(obj_file)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)

    points, face_indices = mesh.sample(num_points, return_index=True)
    normals = mesh.face_normals[face_indices]

    return points, normals


def ply_to_points(ply_file: str, num_points: int = 10000):
    """Read PLY file. If it has more points, downsample. If less, upsample with replacement."""
    if trimesh is None:
        raise ImportError('trimesh is required.')

    pc = trimesh.load(ply_file)

    if hasattr(pc, 'vertices'):
        vertices = np.array(pc.vertices)
        if hasattr(pc, 'vertex_normals') and len(pc.vertex_normals) == len(vertices):
            normals = np.array(pc.vertex_normals)
        else:
            normals = None
    else:
        raise ValueError(f'Could not load vertices from {ply_file}')

    current_n = len(vertices)
    if current_n == num_points:
        pass
    elif current_n > num_points:
        idx = np.random.choice(current_n, num_points, replace=False)
        vertices = vertices[idx]
        if normals is not None:
            normals = normals[idx]
    else:
        idx = np.random.choice(current_n, num_points, replace=True)
        vertices = vertices[idx]
        if normals is not None:
            normals = normals[idx]

    return vertices, normals


def load_and_sample(path: str, num_points: int):
    """Dispatcher for file loading."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ['.stp', '.step']:
        return step_to_points(path, num_points)
    elif ext == '.stl':
        return stl_to_points(path, num_points)
    elif ext == '.obj':
        return obj_to_points(path, num_points)
    elif ext == '.ply':
        return ply_to_points(path, num_points)
    else:
        raise ValueError(f'Unsupported file extension: {ext}')


# -----------------------------------------------------------------------------
# Normalization
# -----------------------------------------------------------------------------


def normalize_pc(points: np.ndarray) -> np.ndarray:
    """Normalize a single point cloud to unit scale."""
    mean = np.mean(points, axis=0)
    centered = points - mean
    scale = np.max(np.abs(centered))
    if scale > 1e-8:
        normalized = centered / scale
    else:
        normalized = centered
    return normalized


def normalize_pc_pair(gt_points: np.ndarray, pred_points: np.ndarray):
    """Normalize both point clouds independently."""
    return normalize_pc(gt_points), normalize_pc(pred_points)


# -----------------------------------------------------------------------------
# Workers for pair processing
# -----------------------------------------------------------------------------


def process_pair(args):
    """
    Worker function to process a single pair of files.
    Args:
        args: tuple containing (gt_path, pred_path, num_points)
    Returns:
        dict with per-shape metrics
    """
    from src.metrics import metrics as m

    gt_path, pred_path, num_points = args
    model_id = Path(gt_path).stem

    try:
        gt_points, gt_normals = load_and_sample(gt_path, num_points)
        pred_points, pred_normals = load_and_sample(pred_path, num_points)

        gt_norm, pred_norm = normalize_pc_pair(gt_points, pred_points)

        gt_tree = cKDTree(gt_norm)
        pred_tree = cKDTree(pred_norm)

        result_metrics = {'model_id': model_id}

        result_metrics['CD'] = (
            m.compute_chamfer_distance(gt_norm, pred_norm, gt_tree=gt_tree, pred_tree=pred_tree) * 1000
        )

        if gt_normals is not None and pred_normals is not None:
            result_metrics['NC'] = m.compute_normal_consistency(
                gt_norm, pred_norm, gt_normals, pred_normals, gt_tree=gt_tree, pred_tree=pred_tree
            )
            result_metrics['NC_unnorm'] = m.compute_normal_consistency(gt_points, pred_points, gt_normals, pred_normals)
            result_metrics['ECD'] = (
                m.edge_chamfer_dist(gt_norm, pred_norm, gt_normals, pred_normals, gt_tree=gt_tree, pred_tree=pred_tree)
                * 1000
            )
        else:
            result_metrics['NC'] = np.nan
            result_metrics['NC_unnorm'] = np.nan
            result_metrics['ECD'] = np.nan

        return result_metrics

    except Exception as e:
        logger.error(f'Error processing {model_id}: {e}')
        return None


# -----------------------------------------------------------------------------
# Multiprocessing helpers
# -----------------------------------------------------------------------------


class NonDaemonProcess(Process):
    def _get_daemon(self):
        return False

    def _set_daemon(self, value):
        pass

    daemon = property(_get_daemon, _set_daemon)


class NonDaemonPool(Pool):
    def Process(self, *args, **kwargs):
        proc = super(NonDaemonPool, self).Process(*args, **kwargs)
        proc.__class__ = NonDaemonProcess
        return proc


def _process_pair_worker(args, result_queue):
    """Worker that puts result into queue."""
    try:
        result_queue.put(process_pair(args))
    except Exception:
        result_queue.put(None)


def process_pair_safe(args, timeout=1200):
    result_queue: Queue = Queue()
    process = Process(target=_process_pair_worker, args=(args, result_queue))
    process.start()
    process.join(timeout)

    if process.is_alive():
        logger.warning('process timeout:', args[0])
        process.terminate()
        process.join()
        return None

    try:
        return result_queue.get_nowait()
    except queue.Empty:
        logger.warning('result queue is empty')
        return None


def find_files(d, ext):
    matches = []
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith(ext):
                matches.append(os.path.join(root, f))
    return matches
