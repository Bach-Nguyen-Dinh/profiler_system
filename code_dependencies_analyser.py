import ast
import os
import glob
import shutil
import networkx as nx
import matplotlib.pyplot as plt
from pyvis.network import Network


def _resolve_local_module(module_name, file_dir, project_root):
    for base in (file_dir, project_root):
        candidate = os.path.join(base, module_name + '.py')
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
        candidate = os.path.join(base, module_name, '__init__.py')
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def _get_local_imports(filepath, project_root):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, OSError):
        return []

    file_dir = os.path.dirname(os.path.abspath(filepath))
    results = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve_local_module(alias.name.split('.')[0], file_dir, project_root)
                if resolved:
                    results.append(resolved)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            resolved = _resolve_local_module(node.module.split('.')[0], file_dir, project_root)
            if resolved:
                results.append(resolved)

    return results


def _collect_all(filepath, project_root, visited=None):
    if visited is None:
        visited = set()
    filepath = os.path.abspath(filepath)
    if filepath in visited:
        return visited
    visited.add(filepath)
    for dep in _get_local_imports(filepath, project_root):
        _collect_all(dep, project_root, visited)
    return visited


def _node_label(filepath):
    return os.path.basename(filepath)


def analyse_dependencies(pathDir, fileType='py', mainFile='main.py'):  # noqa: ARG001 fileType kept for API compat
    main_path = os.path.join(pathDir, mainFile)
    if not os.path.isfile(main_path):
        print(f"Main file not found: {main_path}")
        return

    output_dir = os.path.join(pathDir, "call_dependencies")
    os.makedirs(output_dir, exist_ok=True)

    for old in glob.glob(os.path.join(output_dir, "*.txt")):
        try:
            os.remove(old)
        except Exception as e:
            print(f"Warning: could not remove {old}: {e}")

    # Walk imports recursively; stop at stdlib/third-party (not resolvable as local files)
    all_files = _collect_all(main_path, pathDir)

    for src in all_files:
        name = os.path.basename(src)
        dst = os.path.join(output_dir, os.path.splitext(name)[0] + '.txt')
        try:
            shutil.copy(src, dst)
        except Exception as e:
            print(f"Skipped {name}: {e}")

    # Build directed graph: edge from importer → imported
    g = nx.DiGraph()
    for src in all_files:
        g.add_node(_node_label(src))
        for dep in _get_local_imports(src, pathDir):
            if dep in all_files:
                g.add_edge(_node_label(src), _node_label(dep))

    main_label = mainFile

    net = Network(notebook=True, directed=True, cdn_resources='in_line')
    net.from_nx(g)
    for node in net.nodes:
        if node['id'] == main_label:
            node['color'] = 'orange'

    output_file = os.path.join(pathDir, 'call_dependencies', 'calls.html')
    net.write_html(output_file)
    print(f"\nDependencies analysis saved to: {output_file}")

    node_colors = ['orange' if n == main_label else 'blue' for n in g.nodes()]
    nx.draw_circular(g, with_labels=True, node_color=node_colors)
    plt.draw()
    plt.savefig(os.path.join(pathDir, 'call_dependencies', 'calls.png'), dpi=300)
    plt.close()


if __name__ == "__main__":
    pathDir = input("Enter the directory path to be analysed: ")
    mainFile = input("Enter the main file name (e.g. main.py): ")
    analyse_dependencies(pathDir, mainFile=mainFile)
