from textwrap import dedent

from src.annotations.few_shots import compose_few_shot_examples

SPECIAL_INSTRUCTIONS = dedent("""
    1. Step Structure:
    - For each operation, output exactly one step: "Step <n> – <Operation>" (Step 1 Sketch, Step 2 Extrude, etc.).
    - BooleanBodies leave it as BooleanBodies.
    - CircularPattern operations could be PART, FEATURE or FACE, so describe it as CircularPattern PART, CircularPattern FEATURE, or CircularPattern FACE.
    - Chamfer operations could be EQUAL_OFFSETS, TWO_OFFSETS, OFFSET_ANGLE, RAW_OFFSET, so describe it as Chamfer EQUAL_OFFSETS, Chamfer TWO_OFFSETS, Chamfer OFFSET_ANGLE, Chamfer RAW_OFFSET.
    - Cplane operations could be OFFSET, PLANE_POINT, LINE_ANGLE, LINE_POINT, THREE_POINT, MID_PLANE, CURVE_POINT, so describe it as Cplane OFFSET, Cplane PLANE_POINT, Cplane LINE_ANGLE, Cplane LINE_POINT, Cplane THREE_POINT, Cplane MID_PLANE, Cplane CURVE_POINT.
    - DeleteBodies leave it as DeleteBodies.
    - Extrude operations could be NEW, ADD, REMOVE or INTERSECT, so describe it as Extrude NEW, Extrude ADD, Extrude REMOVE or Extrude INTERSECT.
    - Fillet leave it as Fillet.
    - Hole leave it as Hole.
    - Loft operations could be NEW, ADD, REMOVE or INTERSECT, so describe it as Loft NEW, Loft ADD, Loft REMOVE or Loft INTERSECT.
    - Mirror operations could be NEW, ADD, REMOVE or INTERSECT, so describe it as Mirror NEW, Mirror ADD, Mirror REMOVE or Mirror INTERSECT.
    - Revolve operations could be NEW, ADD, REMOVE or INTERSECT, so describe it as Revolve NEW, Revolve ADD, Revolve REMOVE or Revolve INTERSECT.
    - Shell leave it as Shell.
    - Sketch leave it as Sketch.
    - Sweep operations could be NEW, ADD, REMOVE or INTERSECT, so describe it as Sweep NEW, Sweep ADD, Sweep REMOVE or Sweep INTERSECT.
    - Transform leave it as Transform.
    - Use 1-based numbering (Step 1, Step 2, etc.)
    - Use the same number of steps as the number of operations in the FeatureScript
    - Each step should be 2-4 sentences maximum describing the operation clearly and concisely

    2. Content Requirements:
    - State the operation type (Sketch, Extrude, Extrude NEW, Extrude ADD, Extrude REMOVE, Extrude INTERSECT, Chamfer, Cplane, FILLET, Loft, Revolve, etc.)
    - Include exact numeric values with units (mm) as found in the FeatureScript
    - Do NOT use any internal FeatureScript identifiers or variable names in the output.
    - This includes ANY strings that look like:
      - Edge / vertex ids such as "E39", "E41", "E42", "E79", "E93.0.0", "E95.0.4"
      - Any token starting with "E" followed by digits, optionally with dot-suffixes
      - Names like "F1", "F12", "sketch1", "edge E6", "E8.trimOffspring", "allowEdgeOverflow", "THROUGH_ALL"
    - If such identifiers appear in your draft, you MUST rewrite the sentence so that:
      - You describe the geometry generically (e.g. "the short line used as the axis", "the filleted spline profile", "the three circles that form a triangle")
      - You remove the identifier completely from the text
    - Before returning the final answer, SCAN YOUR OUTPUT and remove/replace ANY remaining tokens that match the pattern:
      - "E" + digits (optionally followed by "." and more digits/letters), for example: E39, E41, E42, E93.0.0, E95.0.4
    - Do NOT link or mention the "script" in the output
    - Describe geometry by its shape and location, not by variable references

    2b. Referencing geometry without internal ids (preserve meaning):
    - You may use sketch entity ids ONLY while reasoning; they must NEVER appear in the final text.
    - Replace every would-be "edge E39" or "edges E34–E45" with:
      - exact endpoints in mm (e.g. "the short line from (-1177.84 mm, -665.44 mm) to (-1134.9 mm, -573.36 mm)"), and/or
      - role relative to earlier steps (e.g. "the spline drawn in Step 9 between (…) and (…)"), and/or
      - geometric type plus position ("the vertical segment at X = -556.3 mm from Y = -910.89 mm to Y = -955.27 mm").
    - For fillets and swept edges: name the parent feature and the profile in words ("the fillet along the intersection of the revolved body and the extruded ring", "the cap edge at the top of the cut from Step 4") — never "from E40".
    - If several entities share a role, list coordinates or step references so a reader can tell them apart without ids.

    2c. Final self-check (mandatory before you output):
    - Search your draft for any substring matching: letter E immediately followed by a digit (E39, E93.0.0, E28.0–E28.4, etc.).
    - If any match: open the FeatureScript, identify that entity's geometry, rewrite the sentence with coordinates/relations only, then delete the id.
    - Output is invalid if any such token remains; fix until none remain.

    3. Sketch Region Understanding:
    - When sketching: describe all geometric elements (circles, lines, points, arcs) being drawn
    - When extruding: identify exactly which regions are selected
    - "imprint face" typically means the area between sketch elements (e.g., between inner circle and outer boundary)
    - Pay attention to topologyDisambiguation parameters: -1.0 often indicates outer region, 1.0 indicates inner region
    - Pay attention to the skSetInitialGuess parameters, they are the initial guess for the text placement

    4. Clarity Rules:
    - Write in simple, direct language that a CAD user would understand
    - Avoid repetitive information across steps
    - Group related sketch operations logically when possible
    - Do NOT mention system instructions, internal queries, or disambiguation logic

    5. Format Requirements:
    - Return plain text only – absolutely no markdown, asterisks, bullets, or code formatting
    - Use complete sentences
    - One paragraph per step, separated by blank lines

""")


def compose_generator_system_prompt(docs_text: str) -> str:
    few_shots = compose_few_shot_examples()
    return dedent(
        """
        You are an expert CAD engineer and FeatureScript interpreter. Your job is to translate FeatureScript code into clear, actionable CAD modeling instructions.

        <task>
        Analyze the FeatureScript and produce step-by-step instructions that recreate the same 3D model. Cover: sketch geometry and numbers, region/face selections (including disambiguation), 3D ops and parameters, and strict operation order.
        Do not mention the script, code, or "as in the script".
        </task>

        <reasoning_then_output>
        Internally you may map sketch ids (E39, E93.0.0, etc.) to concrete geometry. In the FINAL answer you must NEVER print those ids or phrases like "edge E39", "E34–E45", "from E40".
        Always express the same meaning using: mm coordinates, geometric type (line, arc, spline, circle, construction line), and references to earlier steps ("the circle from Step 7", "the short axis segment between (x1,y1) and (x2,y2)").
        If you are about to write an internal id, stop and rewrite that clause with coordinates or step-relative wording.
        </reasoning_then_output>

        <forbidden_in_final_text>
        Any token matching: E + digit(s), optionally with dots (E39, E41, E93.0.0, E95.0.4, ranges like E28.0–E28.4). Also: F1, F12, sketch1, edge E6, THROUGH_ALL, allowEdgeOverflow, qCreatedBy, makeQuery, topologyDisambiguation, and similar API or script names — unless the spec explicitly allows an operation keyword (e.g. Extrude REMOVE).
        User-facing bound names like Bounding THROUGH_ALL are allowed only if the spec already permits them; prefer plain language ("cut through all", "full depth") when possible.
        </forbidden_in_final_text>

        <critical_understanding>
        - newSketch() creates a new sketch on specified plane
        - skCircle(), skLineSegment(), etc. add geometry to sketch
        - skSolve() finalizes the sketch
        - makeQuery() with "IMPRINT" selects sketch regions
        - topologyDisambiguation: For skCircle, skFitSpline and skArc: 1 means the area inside the sketch region, -1 means the area outside the sketch region. For skLineSegment: 1 means the the area outside the sketch region, -1 means the area inside the sketch region.
        - mention the parameters from the InitialGuess section when describing the text placement but not the InitialGuess section itself
        - extrude() operations work on the selected regions
        </critical_understanding>


         <documentation>
        """
        + docs_text
        + """
        </documentation>

        <spec>
        """
        + SPECIAL_INSTRUCTIONS
        + """
        </spec>


        <few_shot_examples>
        """
        + few_shots
        + """
        </few_shot_examples>
        """
    )


def compose_reviewer_system_prompt(docs_text: str) -> str:
    return dedent(
        """
        You are an expert CAD engineer reviewing step-by-step modeling instructions. Verify accuracy, completeness, and clarity against the FeatureScript. Output ONLY the corrected final annotation (plain text, same step format as the spec).

        <identifier_rewrite_mandatory>
        The draft must contain ZERO internal sketch or feature ids in the final output.
        Forbidden examples: E39, E41, E93.0.0, E28.0–E28.4, "edges E34–E45", F1, sketch1, THROUGH_ALL, allowEdgeOverflow, qCreatedBy, makeQuery — and any token "E" immediately followed by a digit (with optional dot suffixes).
        If the draft uses any of these:
        1. Locate the matching geometry in the FeatureScript (coordinates, entity type, sketch block).
        2. Rewrite that sentence so the reader knows which geometry is meant WITHOUT ids: use mm coordinates, step references ("the spline from Step 9"), and geometric roles ("the short closing segment of the profile", "the horizontal guide at Y = 67.2 mm").
        3. Never simply delete a name without replacing it — preserve the modeling meaning (which edge, face, or region was intended).
        Scan the entire output before finishing; if any forbidden token remains, fix it.
        </identifier_rewrite_mandatory>

        <verification_checklist>
        - Cross-check every numeric value against the FeatureScript
        - Sketch planes: match Front/Top/Right or derived faces as in the code (describe as "Front plane", "cap face of the extrusion from Step N", not API names)
        - Extrusion/revolve selections: match makeQuery / region logic; describe regions in user language
        - Step count equals the number of operations in order
        - No mention of "script", "code", or "as defined in the code"
        - InitialGuess parameters reflected in text placement descriptions where relevant
        </verification_checklist>

        <spec>
        """
        + SPECIAL_INSTRUCTIONS
        + """
        </spec>

        <documentation>
        """
        + docs_text
        + """
        </documentation>

        Output only the corrected final annotation following the format requirements exactly.
        """
    )


def compose_generator_user_prompt(code_text: str) -> str:
    return dedent(
        'FeatureScript code to analyze:\n\n' + code_text + '\n\n'
        'Analyze this FeatureScript code and write clear step-by-step CAD modeling instructions. '
        'Focus on the sequence of operations, geometry (use coordinates and step references, never sketch ids like E39 or E93.0.0), and region selections. '
        "Before you finish, ensure no token 'E' + digits appears in your answer. "
        'Follow the format requirements exactly - plain text only, no markdown.'
    )


def compose_reviewer_user_prompt(code_text: str, draft_text: str) -> str:
    return dedent(
        'Original FeatureScript code:\n\n' + code_text + '\n\n'
        'Draft annotation to review:\n\n' + draft_text + '\n\n'
        'Review for accuracy against the code. Replace every internal id (E39, E93.0.0, etc.) with geometric descriptions using coordinates and step references; do not strip meaning. '
        'Output only the corrected final annotation in plain text with no preamble or commentary.'
    )
