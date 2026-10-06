# parts_tray — saved CAD dimensions

All dimensions are in millimeters. STEP contains the editable solid geometry; parameters.json records the applied dimensions.

The STL is the exact verified preview mesh. 3MF uses the same tessellation and millimeter units.

To rebuild with Python, install the pinned dependencies in a virtual environment:

```text
python -m pip install -r requirements.txt
python rebuild.py
```

Edit the parameters object in parameters.json and run rebuild.py again. Outputs go to rebuilt/ beside this file. Canonical source and shared helpers are in sources/. The source defaults describe the original design; rebuild.py applies your saved dimensions. Assembly rebuilds also regenerate the kit's components, sharing the changed dimensions with each part.

SHA256SUMS.json verifies all supplied files. Apache-2.0 licensing applies. Physical printing and performance have not been tested.
