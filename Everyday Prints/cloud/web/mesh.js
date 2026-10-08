export function verifyMesh(buffer, bounds) {
  const unreadable = () => new Error('The mesh file could not be verified. Update the preview to try again.');
  if (buffer.byteLength < 84) throw unreadable();
  const file = new DataView(buffer);
  const triangles = file.getUint32(80, true);
  if (!triangles || buffer.byteLength !== 84 + triangles * 50) throw unreadable();
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let face = 84; face < buffer.byteLength; face += 50) {
    for (let component = 0; component < 12; component++) {
      const value = file.getFloat32(face + component * 4, true);
      if (!Number.isFinite(value)) throw unreadable();
      if (component < 3) continue; // Facet normals precede the three vertices.
      const axis = component % 3;
      min[axis] = Math.min(min[axis], value);
      max[axis] = Math.max(max[axis], value);
    }
  }
  const size = max.map((value, axis) => value - min[axis]);
  if (size.some(value => value <= 0)) throw unreadable();
  // Catalog CAD bounds and STL tessellation differ slightly. Allow 0.05 mm
  // plus one part per million for the file's single-precision coordinates.
  if (size.some((value, axis) => Math.abs(value - bounds[axis]) > .05 + value * 1e-6)) {
    throw new Error('The mesh dimensions do not match the model details. Update the preview to try again.');
  }
}
