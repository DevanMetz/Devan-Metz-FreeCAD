"""Build the offline image gallery and Markdown index from the collection docs.

Uses only Python's standard library and the already saved CAD snapshots.
Run again after changing the catalog or rebuilding review images.
"""
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import quote

from build_collection import NAMES, ASSEMBLIES, current_view_packets

ROOT = Path(__file__).resolve().parent
ASSEMBLY_DETAILS = {
    'soap_dish_assembly': ('Soap dish assembly', 'Tray and draining insert. Print the two components separately.'),
    'sanding_assembly': ('Sanding block assembly', 'Block with two seated wedges. Flexible sandpaper is omitted.'),
    'sliding_box_assembly': ('Sliding box assembly', 'Box with its captured lid 30 mm open. Print box and lid separately.'),
    'ruler_stop_assembly': ('Ruler stop assembly', 'Stop and wedge around an illustrative gray ruler; the ruler is not a print.'),
    'strap_clamp_assembly': ('Strap clamp assembly', 'Four corner pads around a reference frame and strap. Frame and strap are not prints.'),
    'divider_joint_assembly': ('Divider joint assembly', 'Cross connector with four separate reference boards. Only the connector is printed.'),
}

PAGE = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Everyday Prints — visual index</title>
  <style>
    :root { color-scheme: light; --ink:#172f36; --muted:#52676d; --line:#cfdcde; --paper:#f1f5f5; --teal:#006c73; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--paper); color:var(--ink); line-height:1.5; }
    a { color:var(--teal); text-underline-offset:.18em; }
    a:hover { color:#003f45; }
    button,input,select { font:inherit; }
    :focus-visible { outline:3px solid #bf7900; outline-offset:3px; }
    header,main,footer,.controls-inner { width:min(1480px,calc(100% - 48px)); margin:auto; }
    header { padding:42px 0 26px; }
    .eyebrow { color:var(--teal); font-size:.78rem; font-weight:750; letter-spacing:.13em; text-transform:uppercase; margin:0 0 8px; }
    h1 { font-size:clamp(2.2rem,5vw,4rem); letter-spacing:-.055em; line-height:1.08; margin:0 0 14px; }
    .intro { color:var(--muted); margin:0; max-width:780px; }
    .header-links { display:flex; flex-wrap:wrap; gap:12px 22px; margin-top:18px; font-size:.94rem; }
    .controls { position:sticky; top:0; z-index:2; background:#f1f5f5f5; border-block:1px solid var(--line); backdrop-filter:blur(8px); }
    .controls-inner { padding:16px 0; display:grid; grid-template-columns:minmax(200px,1fr) minmax(170px,290px) auto; gap:12px; align-items:end; }
    label { display:block; color:var(--muted); font-size:.8rem; font-weight:650; margin-bottom:5px; }
    input,select { width:100%; min-height:44px; border:1px solid #9eb6bc; border-radius:8px; padding:9px 12px; background:white; color:var(--ink); }
    .types { display:flex; gap:5px; flex-wrap:wrap; }
    .types button,.reset { cursor:pointer; border:1px solid #9eb6bc; border-radius:8px; padding:10px 13px; background:white; color:var(--ink); min-height:44px; }
    .types button[aria-pressed="true"] { background:var(--ink); border-color:var(--ink); color:white; }
    .types button:hover { border-color:var(--teal); }
    .results { display:flex; justify-content:space-between; gap:16px; margin:22px 0 15px; color:var(--muted); font-size:.9rem; }
    .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(270px,1fr)); gap:20px; }
    .card { background:white; border:1px solid var(--line); border-radius:12px; overflow:hidden; align-self:start; scroll-margin-top:160px; }
    .card:target { outline:3px solid #bf7900; outline-offset:3px; }
    .thumbnail { display:block; background:#edf3f5; overflow:hidden; }
    .thumbnail img { display:block; width:100%; height:auto; aspect-ratio:4/3; object-fit:contain; transition:transform .18s ease; }
    .thumbnail:hover img { transform:scale(1.025); }
    .content { padding:16px; }
    .meta { display:flex; flex-wrap:wrap; gap:7px; align-items:center; margin-bottom:9px; }
    .badge { background:#e2f1ef; color:#075c62; border-radius:5px; padding:3px 7px; font-size:.7rem; font-weight:750; letter-spacing:.02em; }
    .badge.reference { background:#fff0da; color:#775100; }
    .number { font-size:.75rem; color:var(--muted); }
    h2 { font-size:1.08rem; line-height:1.3; letter-spacing:-.015em; margin:0 0 8px; }
    h2 a { color:var(--ink); text-decoration:none; }
    h2 a:hover { text-decoration:underline; }
    .spec { color:var(--muted); font-size:.86rem; margin:0 0 10px; min-height:3em; }
    .category { color:var(--muted); font-size:.72rem; margin:0 0 14px; }
    .files { display:flex; flex-wrap:wrap; gap:7px; }
    .files a { font-size:.8rem; border:1px solid var(--line); padding:5px 9px; border-radius:5px; text-decoration:none; }
    .files a:hover { background:#edf6f5; border-color:#8eafb4; }
    details { margin-top:14px; border-top:1px solid var(--line); padding-top:10px; }
    summary { cursor:pointer; color:var(--teal); font-size:.82rem; }
    .views { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; margin-top:10px; }
    .views img { display:block; width:100%; height:auto; aspect-ratio:4/3; object-fit:contain; background:#edf3f5; }
    .views a { font-size:.68rem; text-align:center; }
    .empty { text-align:center; padding:60px 20px; border:1px dashed #9eb6bc; border-radius:12px; }
    [hidden] { display:none!important; }
    footer { padding:36px 0; color:var(--muted); font-size:.85rem; }
    footer p { margin:0 0 8px; }
    .notice { font-size:.83rem; color:var(--muted); margin-top:16px; }
    @media (max-width:900px) { .controls-inner { grid-template-columns:1fr 1fr; } .types { grid-column:1/-1; } .card { scroll-margin-top:220px; } }
    @media (max-width:540px) { header,main,footer,.controls-inner { width:calc(100% - 28px); } header { padding-top:28px; } .controls-inner { grid-template-columns:1fr; gap:9px; } .controls { position:static; } .grid { grid-template-columns:1fr; } .results { flex-direction:column; gap:3px; } .spec { min-height:0; } }
    @media (prefers-reduced-motion:reduce) { .thumbnail img { transition:none; } }
    @media print { .controls,.header-links,.files,details,.empty { display:none; } .grid { grid-template-columns:repeat(3,1fr); gap:12px; } .card { break-inside:avoid; } .spec { min-height:0; } header { padding-top:0; } }
  </style>
</head>
<body>
  <header>
    <p class="eyebrow">Visual model index · open source CAD</p>
    <h1>Everyday Prints</h1>
    <p class="intro">__PRINT_COUNT__ adjustable print files and __ASSEMBLY_COUNT__ assembly references. Browse the actual CAD previews, choose a model, and open its print files or editable source.</p>
    <nav class="header-links" aria-label="Collection links">
      <a href="everyday-prints.zip" download>Download the collection</a>
      <a href="README.md">Printing &amp; customization guide</a>
      <a href="INDEX.md">Markdown image index</a>
      <a href="LICENSE">Apache-2.0 license</a>
    </nav>
    <p class="notice">Dimensions are in millimeters. Images show CAD geometry; physical print testing is pending.</p>
  </header>
  <div class="controls">
    <div class="controls-inner">
      <div><label for="search">Find a model</label><input id="search" type="search" placeholder="Try cable, divider, jig…" autocomplete="off"></div>
      <div><label for="category">Category</label><select id="category"><option value="">All categories</option>__CATEGORIES__</select></div>
      <div class="types" role="group" aria-label="Model type">
        <button type="button" data-kind="" aria-pressed="true">All · __TOTAL__</button>
        <button type="button" data-kind="print" aria-pressed="false">Prints · __PRINT_COUNT__</button>
        <button type="button" data-kind="assembly" aria-pressed="false">Assemblies · __ASSEMBLY_COUNT__</button>
      </div>
    </div>
  </div>
  <main>
    <div class="results"><span id="count" role="status" aria-live="polite">__TOTAL__ models</span><span>Select an image for the full-size view.</span></div>
    <noscript><p>All models are shown below. Search and filters need JavaScript; the images and file links work without it.</p></noscript>
    <div class="grid">__CARDS__</div>
    <div class="empty" hidden><p>No models match those filters.</p><button type="button" class="reset">Clear filters</button></div>
  </main>
  <footer>
    <p>Assembly references show how parts fit together. Print their separate components; gray reference hardware and the strap loop are not print files.</p>
    <p>Sources are parametric Python. STEP is exchange geometry; STL and 3MF are print meshes. 3MF files contain geometry and units.</p>
    <p><a href="THREAD_SUMMARY.md">Complete design inventory and verification summary</a> · <a href="README.md">Use instructions</a></p>
  </footer>
  <script>
    const cards = Array.from(document.querySelectorAll('.card'));
    const search = document.querySelector('#search');
    const category = document.querySelector('#category');
    const buttons = Array.from(document.querySelectorAll('.types button'));
    let kind = '';
    function filter() {
      const terms = search.value.trim().toLocaleLowerCase().split(/\\s+/).filter(Boolean);
      let visible = 0;
      cards.forEach(card => {
        const matches = (!kind || card.dataset.kind === kind)
          && (!category.value || card.dataset.category === category.value)
          && terms.every(term => card.dataset.search.includes(term));
        card.hidden = !matches;
        if (matches) visible++;
      });
      document.querySelector('#count').textContent = `${visible} of ${cards.length} models`;
      document.querySelector('.empty').hidden = visible !== 0;
    }
    search.addEventListener('input', filter);
    category.addEventListener('change', filter);
    buttons.forEach(button => button.addEventListener('click', () => {
      kind = button.dataset.kind;
      buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      filter();
    }));
    document.querySelector('.reset').addEventListener('click', () => {
      search.value = ''; category.value = ''; kind = '';
      buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.kind === '')));
      filter(); search.focus();
    });
  </script>
</body>
</html>
'''


def catalog():
    rows = {}
    for line in (ROOT/'README.md').read_text(encoding='utf-8').splitlines():
        if not line.startswith('|'):
            continue
        match = re.search(r'\((\w+)\.stl\)',line)
        if match:
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            rows[match[1]] = (cells[0],cells[1])
    assert set(rows) == set(NAMES), 'Every print file needs a guide table row.'
    groups = {}
    for line in (ROOT/'THREAD_SUMMARY.md').read_text(encoding='utf-8').splitlines():
        names = re.findall(r'`(\w+)`',line)
        if line.startswith('|') and names:
            category = line.split('|')[1].strip().rsplit(' — ',1)[0]
            for name in names:
                groups[name] = category
    assert set(groups) == set(NAMES), 'Every print file needs an inventory category.'
    jobs = {Path(job['input']).name.removesuffix('.step.py'):job for job in current_view_packets()}
    items = []
    for number,name in enumerate(NAMES+ASSEMBLIES,1):
        if name in NAMES:
            title,spec = rows[name]
            category,kind = groups[name],'print'
        else:
            title,description = ASSEMBLY_DETAILS[name]
            facts = json.loads((ROOT/f'review/{name}.facts.json').read_text(encoding='utf-8-sig'))
            size = facts['tokens'][0]['entryFacts']['size']
            spec = ' × '.join(f'{value:.2f}'.rstrip('0').rstrip('.') for value in size)+' mm. '+description
            category,kind = 'Reference assemblies','assembly'
        images = [Path(view['path']).relative_to(ROOT).as_posix() for view in jobs[name]['outputs']]
        files = [(suffix.upper(),name+'.'+suffix) for suffix in (('stl','3mf','step') if kind=='print' else ('step',))]
        files.append(('Source',name+'.step.py'))
        for path in images+[path for _,path in files]:
            if not (ROOT/path).is_file():
                raise FileNotFoundError(path)
        items.append(dict(number=number,name=name,title=title,spec=spec,category=category,
                          kind=kind,images=images,files=files))
    return items


def card(item):
    image,title = item['images'][0],item['title']
    search = ' '.join([item['name'].replace('_',' '),item['name'],title,item['spec'],item['category']]).lower()
    files = ''.join(f'<a href="{quote(path)}"'+(' download' if path.endswith(('.stl','.3mf')) else '')
                    +f'>{escape(label)}</a>' for label,path in item['files'])
    views = ''.join(f'<a href="{quote(path)}" target="_blank" rel="noopener"><img src="{quote(path)}" '
                    f'width="1000" height="750" loading="lazy" alt="{escape(title)} — {label}">{label}</a>'
                    for label,path in zip(('Underside / opposite','Top','Front'),item['images'][1:]))
    reference = item['kind']=='assembly'
    badge = 'Assembly · view only' if reference else 'Print file'
    return f'''<article class="card" id="{item['name']}" data-kind="{item['kind']}" data-category="{escape(item['category'])}" data-search="{escape(search)}">
      <a class="thumbnail" href="{quote(image)}" target="_blank" rel="noopener" aria-label="Full-size CAD view of {escape(title)}"><img src="{quote(image)}" alt="{escape(title)}" width="1000" height="750" loading="lazy"></a>
      <div class="content">
        <div class="meta"><span class="badge{' reference' if reference else ''}">{badge}</span><span class="number">{item['number']:02d}</span></div>
        <h2><a href="#{item['name']}">{escape(title)}</a></h2>
        <p class="spec">{escape(item['spec'])}</p>
        <p class="category">{escape(item['category'])}</p>
        <div class="files">{files}</div>
        <details><summary>Three more CAD views</summary><div class="views">{views}</div></details>
      </div>
    </article>'''


def main():
    items = catalog()
    categories = list(dict.fromkeys(item['category'] for item in items))
    html = PAGE.replace('__CARDS__','\n'.join(card(item) for item in items))
    html = html.replace('__CATEGORIES__',''.join(f'<option>{escape(label)}</option>' for label in categories))
    html = html.replace('__TOTAL__',str(len(items))).replace('__PRINT_COUNT__',str(len(NAMES)))
    html = html.replace('__ASSEMBLY_COUNT__',str(len(ASSEMBLIES)))
    (ROOT/'index.html').write_text(html,encoding='utf-8')
    markdown = ['# Everyday Prints — image index','',
                f'All **{len(NAMES)} print files and {len(ASSEMBLIES)} reference assemblies**, with CAD previews.',
                '[Searchable gallery](index.html) · [Printing guide](README.md) · [Download collection](everyday-prints.zip)','',
                'Dimensions are mm. Physical print testing remains pending. Click an image for the full-size CAD view.','']
    for category in categories:
        markdown.extend(['## '+category,'','| CAD preview | Model and files |','|---|---|'])
        for item in (item for item in items if item['category']==category):
            image = quote(item['images'][0])
            files = ' · '.join(f'[{label}]({quote(path)})' for label,path in item['files'])
            views = ' · '.join(f'[{label}]({quote(path)})' for label,path in zip(('Opposite','Top','Front'),item['images'][1:]))
            title = item['title'].replace('|','\\|')
            spec = item['spec'].replace('|','\\|')
            markdown.append(f'| [![{title}]({image})]({image}) | **[{title}](index.html#{item["name"]})**<br>{spec}<br>{files}<br>{views} |')
        markdown.append('')
    (ROOT/'INDEX.md').write_text('\n'.join(markdown)+'\n',encoding='utf-8')
    print(f'Saved index.html and INDEX.md: {len(items)} models, {len(items)*4} image references.')


if __name__ == '__main__':
    main()
