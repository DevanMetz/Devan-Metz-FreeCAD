"""Verify the installed toolchain audit and patched native image-processing path."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

CLOUD = Path(__file__).resolve().parent
ROOT = CLOUD.parent
TOOLS = ['cf', '@cloudflare/vite-plugin', 'vite', 'typescript', 'miniflare', 'cf/node_modules/miniflare']

NATIVE = r"""
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import sharp from 'sharp';
const lock = JSON.parse(readFileSync('package-lock.json', 'utf8'));
assert.equal(sharp.versions.sharp, lock.packages['node_modules/sharp'].version);
const rsvg = sharp.versions.rsvg.split('.').map(Number);
assert.ok(rsvg[0] > 2 || rsvg[0] === 2 && (rsvg[1] > 63 || rsvg[1] === 63 && rsvg[2] >= 2), sharp.versions.rsvg);
const svg = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="17" height="11"><rect width="17" height="11" fill="#287468"/></svg>');
const rgba = await sharp(svg).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
assert.equal(rgba.info.width, 17);
assert.equal(rgba.info.height, 11);
assert.equal(rgba.info.channels, 4);
assert.deepEqual([...rgba.data.subarray(0, 4)], [40, 116, 104, 255]);
const formats = [];
for (const format of ['png', 'jpeg', 'webp', 'avif']) {
  const encoded = await sharp(svg).toFormat(format).toBuffer();
  const metadata = await sharp(encoded).metadata();
  assert.equal(metadata.width, 17);
  assert.equal(metadata.height, 11);
  assert.ok((format === 'avif' ? ['heif', 'avif'] : [format]).includes(metadata.format));
  await sharp(encoded).raw().toBuffer();
  formats.push({ format, decoded_format: metadata.format, width: metadata.width, height: metadata.height });
}
const images = [];
const catalog = JSON.parse(readFileSync('public/catalog.json', 'utf8'));
assert.equal(catalog.models.length, 53);
for (const item of catalog.models) {
  const path = 'public/' + item.image.replace(/^\//, '');
  const input = readFileSync(path), metadata = await sharp(input).metadata();
  assert.equal(metadata.format, 'png');
  assert.ok(metadata.width > 0 && metadata.height > 0);
  const decoded = await sharp(input).resize(48, 48, { fit: 'inside' }).png().toBuffer({ resolveWithObject: true });
  assert.ok(decoded.info.width > 0 && decoded.info.width <= 48 && decoded.info.height > 0 && decoded.info.height <= 48);
  const digest = createHash('sha256').update(input).digest('hex');
  assert.equal(createHash('sha256').update(readFileSync(path)).digest('hex'), digest);
  images.push({ model: item.name, source_sha256: digest, width: metadata.width, height: metadata.height,
    decoded_width: decoded.info.width, decoded_height: decoded.info.height });
}
console.log(JSON.stringify({ versions: sharp.versions, svg_rgba: [...rgba.data.subarray(0, 4)], formats, images }));
"""


def main():
    node = shutil.which('node')
    npm = shutil.which('npm.cmd' if shutil.which('npm.cmd') else 'npm')
    assert node and npm, 'Use the configured Node/npm runtime.'
    npm_cli = Path(npm).resolve().parent / 'node_modules/npm/bin/npm-cli.js'
    assert npm_cli.is_file(), f'Missing npm CLI: {npm_cli}'
    audit_run = subprocess.run([node, str(npm_cli), 'audit', '--include=dev', '--json'], cwd=CLOUD,
                               capture_output=True, text=True, encoding='utf-8', timeout=60)
    audit = json.loads(audit_run.stdout)
    assert audit_run.returncode == 0 and audit['metadata']['vulnerabilities']['total'] == 0 and not audit['vulnerabilities'], audit
    lock = json.loads((CLOUD/'package-lock.json').read_text(encoding='utf-8'))
    package = json.loads((CLOUD/'package.json').read_text(encoding='utf-8'))
    assert package['overrides']['sharp'] == '^0.35.5' and package['overrides']['undici'] == '^7.29.1'
    assert lock['packages']['node_modules/sharp']['version'] == '0.35.5'
    native_packages = {key: value['version'] for key, value in lock['packages'].items() if key.startswith('node_modules/@img/sharp-')}
    assert len(native_packages) >= 20
    for key, version in native_packages.items():
        assert version == ('1.3.4' if '/sharp-libvips-' in key else '0.35.5'), (key, version)
    baseline = json.loads((ROOT/'review/cloud_dependency_audit_baseline.json').read_text(encoding='utf-8'))
    original_lock = subprocess.check_output(['git', 'show', baseline['head'] + ':Everyday Prints/cloud/package-lock.json'], cwd=ROOT)
    original = json.loads(original_lock)
    tool_versions = {name: lock['packages']['node_modules/' + name]['version'] for name in TOOLS}
    assert all(version == original['packages']['node_modules/' + name]['version'] for name, version in tool_versions.items())
    native_run = subprocess.run([node, '--input-type=module', '-e', NATIVE], cwd=CLOUD,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert native_run.returncode == 0, native_run.stderr
    native = json.loads(native_run.stdout)
    report = {'advisory': baseline['advisory'], 'baseline_head': baseline['head'],
              'baseline_lock_sha256': hashlib.sha256(original_lock).hexdigest(),
              'lock_sha256': hashlib.sha256((CLOUD/'package-lock.json').read_bytes()).hexdigest(),
              'audit_summary': audit['metadata']['vulnerabilities'], 'tool_versions': tool_versions,
              'native_packages': native_packages, 'native': native,
              'checks': ['full_dependency_audit', 'patched_platform_lock', 'retained_toolchain_versions',
                         'patched_svg_decoder', 'four_image_output_formats', 'all_53_catalog_images']}
    (ROOT/'review/cloud_dependency_validation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'vulnerabilities': report['audit_summary']['total'], 'sharp': native['versions']['sharp'],
                      'rsvg': native['versions']['rsvg'], 'platform_packages': len(native_packages),
                      'image_formats': len(native['formats']), 'catalog_images': len(native['images'])}))


if __name__ == '__main__':
    main()
