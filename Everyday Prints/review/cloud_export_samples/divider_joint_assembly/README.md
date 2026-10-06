# divider_joint_assembly — saved CAD dimensions

All dimensions are in millimeters. STEP contains the editable solid geometry; parameters.json records the applied dimensions.

The root STEP is a reference assembly. Print the files in parts/ separately in their saved bed orientation. Illustrative hardware is excluded; there is no combined assembly print mesh.

| Part | Quantity | Use |
| --- | ---: | --- |
| divider_joint | 1 | Assembly component |

Each folder contains STEP, STL, 3MF, and its applied parameters. Print the indicated number of copies; repeated parts share one file.

To rebuild with Python, install the pinned dependencies in a virtual environment:

```text
python -m pip install -r requirements.txt
python rebuild.py
```

Edit the parameters object in parameters.json and run rebuild.py again. Outputs go to rebuilt/ beside this file. Canonical source and shared helpers are in sources/. The source defaults describe the original design; rebuild.py applies your saved dimensions. Assembly rebuilds also regenerate the kit's components, sharing the changed dimensions with each part.

SHA256SUMS.json verifies all supplied files. Apache-2.0 licensing applies. Physical printing and performance have not been tested.
