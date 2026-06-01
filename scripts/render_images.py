import argparse
import multiprocessing
import os
from glob import glob

import numpy as np
import open3d
import skimage
import trimesh
from PIL import Image, ImageOps
from tqdm import tqdm

open3d.utility.set_verbosity_level(open3d.utility.VerbosityLevel.Error)


def mesh_to_image(mesh, camera_distance=-1.8, front=[1, 1, 1], width=1024, height=1024, img_size=128):
    vis = open3d.visualization.Visualizer()
    vis.create_window(width=width, height=height, visible=False)
    vis.add_geometry(mesh)
    lookat = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    front_array = np.array(front, dtype=np.float32)
    up = np.array([0, 1, 0], dtype=np.float32)

    eye = lookat + front_array * camera_distance
    right = np.cross(up, front_array)
    right /= np.linalg.norm(right)
    true_up = np.cross(front_array, right)
    rotation_matrix = np.column_stack((right, true_up, front_array)).T
    extrinsic = np.eye(4)
    extrinsic[:3, :3] = rotation_matrix
    extrinsic[:3, 3] = -rotation_matrix @ eye

    view_control = vis.get_view_control()
    camera_params = view_control.convert_to_pinhole_camera_parameters()
    camera_params.extrinsic = extrinsic
    view_control.convert_from_pinhole_camera_parameters(camera_params)

    vis.poll_events()
    vis.update_renderer()
    image = vis.capture_screen_float_buffer(do_render=True)
    vis.destroy_window()

    image = np.asarray(image)
    image = (image * 255).astype(np.uint8)
    image = skimage.transform.resize(
        image, output_shape=(img_size, img_size), order=2, anti_aliasing=True, preserve_range=True
    ).astype(np.uint8)

    return Image.fromarray(image)


def render_img(args):
    input_path, output_path = args
    model_id = os.path.basename(input_path)
    try:
        mesh = trimesh.load(input_path)
        bbox_center = (mesh.bounds[0] + mesh.bounds[1]) / 2.0
        mesh.apply_translation(-bbox_center)
        transform_scale = 1.0 / mesh.extents.max()
        mesh.apply_scale(transform_scale)
        mesh.apply_translation((0.5, 0.5, 0.5))

        vertices = np.asarray(mesh.vertices)
        faces = np.asarray(mesh.faces)
        mesh = open3d.geometry.TriangleMesh()
        mesh.vertices = open3d.utility.Vector3dVector(vertices)
        mesh.triangles = open3d.utility.Vector3iVector(faces)
        mesh.paint_uniform_color(np.array([255, 255, 136]) / 255.0)
        mesh.compute_vertex_normals()
    except Exception:
        return model_id

    fronts = [[1, 1, 1], [-1, -1, -1], [-1, 1, -1], [1, -1, 1]]
    images = [mesh_to_image(mesh, camera_distance=-0.9, front=front, img_size=256) for front in fronts]
    images = [ImageOps.expand(image, border=5, fill='black') for image in images]
    image = Image.fromarray(
        np.vstack(
            (
                np.hstack((np.array(images[0]), np.array(images[1]))),
                np.hstack((np.array(images[2]), np.array(images[3]))),
            )
        )
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    image.save(output_path)
    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_dir', required=True, help='Input dir with STL files as input_dir/<id[:4]>/<id>.stl')
    parser.add_argument('--output_dir', required=True, help='Output dir of PNG images as output_dir/<id[:4]>/<id>.png')
    parser.add_argument('--start', type=int, default=0, help='Start of chunk_id range [0, 100)')
    parser.add_argument('--stop', type=int, default=100, help='Stop of chunk_id range [0, 100)')
    args = parser.parse_args()

    stl_files = sorted(glob(os.path.join(args.input_dir, '????', '*.stl')))
    job_args = []
    for stl_path in stl_files:
        chunk_id = os.path.basename(os.path.dirname(stl_path))
        if not (args.start <= int(chunk_id) < args.stop):
            continue
        model_id = os.path.splitext(os.path.basename(stl_path))[0]
        output_path = os.path.join(args.output_dir, chunk_id, f'{model_id}.png')
        job_args.append((stl_path, output_path))

    print(f'Rendering {len(job_args)} files (chunks {args.start}–{args.stop - 1})')
    num_cpus = multiprocessing.cpu_count()
    convert_iter = multiprocessing.Pool(num_cpus).imap(render_img, job_args)
    bad_ids = [r for r in tqdm(convert_iter, total=len(job_args)) if r is not None]
    print(f'Failed: {len(bad_ids)}')
    if bad_ids:
        np.save('render_failed.npy', bad_ids)
