import logging
from pathlib import Path

from src.api.client import Client

logger = logging.getLogger(__name__)


def postprocess_code(text: str) -> str:
    """
    Fix limited context length - drop last unfinished operation
    """
    text = text.strip()
    if text.endswith('});'):
        return text
    i = text.rfind('        {')
    return text[:i] + '    });'


def render_document(
    os_client: Client,
    input_dir: Path,
    output_dir: Path,
    filepath: Path,
    doc_id: str,
    ws_id: str,
    ps_id: str,
    fs_id: str,
    export: bool = False,
    postprocessing: bool = False,
) -> int:
    """
    Upload FeatureScript code to an OnShape FeatureStudio, instantiate it as a
    feature in a PartStudio, and record the outcome via sentinel files.

    Outcome files written to output_dir / doc_chunk:
      <name>_c.txt  — compilation error (featureSpecs is empty)
      <name>_r.txt  — rendering error
      <name>_ok.txt — success, no export requested
      <name>.step   — success with STEP geometry exported

    Returns:
        Remaining OnShape API quota after the last request.
    """
    doc_name = filepath.stem
    doc_chunk = filepath.parts[0] if len(filepath.parts) == 2 else ''
    # Read the code
    with open(input_dir / filepath) as f:
        doc_text = f.read()
    if postprocessing:
        doc_text = postprocess_code(doc_text)
    # Upload fs code to FeatureStudio
    res = os_client.post_fs_code(doc_id, ws_id, fs_id, doc_text)
    remains_requests = int(res.headers['X-Rate-Limit-Remaining'])
    # Now we can add FeatureStudio model to the PartStudio
    # 1. get model information
    res = os_client.get_fs_code_specs(doc_id, ws_id, fs_id).json()
    if len(res['featureSpecs']) == 0:
        with open(output_dir / doc_chunk / f'{doc_name}_c.txt', 'w') as f:
            f.write('incorrect FS code: compilation')
        return remains_requests
    specs = res['featureSpecs'][0]
    feature = {
        'btType': 'BTMFeature-134',
        'namespace': specs['namespace'],
        'name': specs['featureTypeName'],
        'featureType': specs['featureType'],
    }
    # 2. Add model to the PartStudio document
    res = os_client.add_feature(doc_id, ws_id, ps_id, feature)
    remains_requests = int(res.headers['X-Rate-Limit-Remaining'])
    res = res.json()
    feature_status = res['featureState']['featureStatus']
    fid = res['feature']['featureId']
    if feature_status == 'ERROR':
        with open(output_dir / doc_chunk / f'{doc_name}_r.txt', 'w') as f:
            f.write('incorrect FS code: rendering')
    # 3. Feature renders fine -> export
    elif export:
        res, remains_requests = os_client.export_step(doc_id, ws_id, ps_id)
        if res is None:
            with open(output_dir / doc_chunk / f'{doc_name}_r.txt', 'w') as f:
                f.write('incorrect FS code: rendering')
        else:
            with open(output_dir / doc_chunk / f'{doc_name}.step', 'wb') as f:
                f.write(res.content)
        # res = os_client.part_studio_stl(doc_id, ws_id, ps_id)
        # if res.status_code == 200:
        #     with open(output_dir / doc_chunk / f'{doc_name}.stl', 'w') as f:
        #         f.write(res.text)
        # else:
        #     print(res.json())
        #     remains_requests = 0
    else:
        with open(output_dir / doc_chunk / f'{doc_name}_ok.txt', 'w') as f:
            f.write('correct FS code')
    os_client.delete_feature(doc_id, ws_id, ps_id, fid)
    return remains_requests
