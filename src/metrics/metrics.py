import numpy as np
from scipy.spatial import cKDTree


def compute_chamfer_distance(gt_points, pred_points, gt_tree=None, pred_tree=None):
    """Compute bidirectional Chamfer Distance (squared)."""
    if pred_tree is None:
        gen_points_kd_tree = cKDTree(pred_points)
    else:
        gen_points_kd_tree = pred_tree

    one_distances, _ = gen_points_kd_tree.query(gt_points)
    gt_to_gen_chamfer = np.mean(np.square(one_distances))

    if gt_tree is None:
        gt_points_kd_tree = cKDTree(gt_points)
    else:
        gt_points_kd_tree = gt_tree

    two_distances, _ = gt_points_kd_tree.query(pred_points)
    gen_to_gt_chamfer = np.mean(np.square(two_distances))

    return gt_to_gen_chamfer + gen_to_gt_chamfer


def compute_normal_consistency(gt_points, pred_points, gt_normals, pred_normals, gt_tree=None, pred_tree=None):
    """Compute Normal Consistency."""
    if gt_tree is None:
        gt_tree = cKDTree(gt_points)
    _, match_pred_gt = gt_tree.query(pred_points, k=1)

    if pred_tree is None:
        pred_tree = cKDTree(pred_points)
    _, match_gt_pred = pred_tree.query(gt_points, k=1)

    normals_dot_pred_gt = np.sum(pred_normals * gt_normals[match_pred_gt], axis=1).mean()
    normals_dot_gt_pred = np.sum(gt_normals * pred_normals[match_gt_pred], axis=1).mean()

    normal_consistency = (normals_dot_pred_gt + normals_dot_gt_pred) / 2
    return normal_consistency


def edge_chamfer_dist(gt_points, gen_points, gt_normals, gen_normals, gt_tree=None, pred_tree=None):
    """
    Compute Edge Chamfer Distance between two point clouds using normals.
    This function detects edge points based on normal variation and computes CD only for edges.
    """
    EF1_RADIUS = 0.004
    EF1_DOTPRODUCT_THRESHOLD = 0.2

    if gt_tree is None:
        gt_tree = cKDTree(gt_points)
    indslist = gt_tree.query_ball_point(gt_points, EF1_RADIUS)
    flags = np.zeros([len(gt_points)], np.bool_)
    for p in range(len(gt_points)):
        inds = indslist[p]
        if len(inds) > 0:
            this_normals = gt_normals[p : p + 1]
            neighbor_normals = gt_normals[inds]
            dotproduct = np.abs(np.sum(this_normals * neighbor_normals, axis=1))
            if np.any(dotproduct < EF1_DOTPRODUCT_THRESHOLD):
                flags[p] = True
    gt_edge_points = np.ascontiguousarray(gt_points[flags])

    if pred_tree is None:
        pred_tree = cKDTree(gen_points)
    indslist = pred_tree.query_ball_point(gen_points, EF1_RADIUS)
    flags = np.zeros([len(gen_points)], np.bool_)
    for p in range(len(gen_points)):
        inds = indslist[p]
        if len(inds) > 0:
            this_normals = gen_normals[p : p + 1]
            neighbor_normals = gen_normals[inds]
            dotproduct = np.abs(np.sum(this_normals * neighbor_normals, axis=1))
            if np.any(dotproduct < EF1_DOTPRODUCT_THRESHOLD):
                flags[p] = True
    pred_edge_points = np.ascontiguousarray(gen_points[flags])

    if len(pred_edge_points) == 0:
        if len(gt_edge_points) == 0:
            return 0.0
        else:
            pred_edge_points = np.zeros((1, 3), dtype=np.float32)

    if len(gt_edge_points) == 0:
        return 0.0

    tree = cKDTree(pred_edge_points)
    dist, _ = tree.query(gt_edge_points, k=1)
    dist = np.square(dist)
    gt2pred_mean_ecd = np.mean(dist)

    tree = cKDTree(gt_edge_points)
    dist, _ = tree.query(pred_edge_points, k=1)
    dist = np.square(dist)
    pred2gt_mean_ecd = np.mean(dist)

    ecd = gt2pred_mean_ecd + pred2gt_mean_ecd
    return ecd
