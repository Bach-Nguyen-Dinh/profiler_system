import matplotlib.pyplot as plt
import os
import glob
from fnmatch import fnmatch
import shutil
import networkx as nx
from pyvis.network import Network

def analyse_dependencies(pathDir, fileType='py', mainFile='main.py'): 
    # --- Files or patterns to ignore ---
    ignore_files = {
        "analyzer.py",
        "code_dependencies_analyser.py",
        "system_metrics.py",
        "system_metrics_topaz.py",
        "plotting.py",
        "integrated_profiler_system.py",
        "test_profiler_use.py"
    }
    #Load all files and append to a list
    if os.path.exists(pathDir):
        if fileType in ['py', 'txt', 'm']: 
            fileType = f"*.{fileType}"
            output_dir = os.path.join(pathDir, "call_dependencies")
            os.makedirs(output_dir, exist_ok=True)

            # --- Clean up previous .txt files before new analysis ---
            for old_file in glob.glob(os.path.join(output_dir, "*.txt")):
                try:
                    os.remove(old_file)
                except Exception as e:
                    print(f"Warning: could not remove {old_file}: {e}")

            for path, subdirs, files in os.walk(pathDir):
                for name in files:
                    # --- Skip ignored files ---
                    if any(fnmatch(name, pattern) for pattern in ignore_files):
                        continue

                    if fnmatch(name, fileType):
                        try:
                            src = os.path.join(path, name)
                            dst = os.path.join(output_dir, name)
                            shutil.copy(src, dst)

                            prefix = os.path.splitext(name)[0]
                            os.rename(dst, os.path.join(output_dir, f"{prefix}.txt"))
                        except Exception as e:
                            print(f"Skipped {name}: {e}")
                            continue

            paths = glob.glob(pathDir+"/call_dependencies/*.txt*")
            files = dict()
            for path in paths:
                with open(path) as f:
                    files[path.split("/")[-1]] = [(line) for line in f.readlines()]

            #Find the functions in each file
            functions = dict()
            
            for key in list(files.keys()):
                functions[key] = []
                for line in files[key]:
                    if fileType == "*.m":
                        if 'function' in line.split(" ") and "%" not in line:
                            # print(line)
                            funcName = line.split("=")[1]
                            functions[key].append(funcName)
                    if fileType == "*.py":
                        # print("Finding python functions")
                        if 'def' in line.split(" ") and "#" != line[0] and "import" not in line and "__init__" not in line:
                            funcName = line.split()[1].split("(")[0]
                            if funcName != '':
                                functions[key].append(funcName)
                        #Finding python classes
                        if "class" in line:
                            functions[key].append(line.split(" ")[-1])
                            if ":" in functions[key][-1]:
                                functions[key][-1] = functions[key][-1].split(":")[0]
            # print(functions)
            #Find the scripts which call other files
            callDepends = dict()
            allFuncs = dict()
            for key in list(functions.keys()):
                for i in  range(len(functions[key])):
                    funcName = functions[key][i].split("(")[0] 
                    
                    if " " in funcName:
                        fName = funcName.split()[0]
                    else:
                        fName = funcName
                    # print(fName)
                    allFuncs[fName] = key
                

            for key in list(files.keys()):
                callDepends[key] = []
                for line in files[key]:
                    for fName in list(allFuncs.keys()):
                        if fName in line and allFuncs[fName] != key:
                            callDepends[key].append(allFuncs[fName])
                callDepends[key] = list(set(callDepends[key]))

            # plot dependencies
            g = nx.DiGraph()
            g.add_nodes_from(callDepends.keys())
            for k, v in callDepends.items():
                g.add_edges_from(([(k, t) for t in v]))

            net = Network(notebook=True, directed=True, cdn_resources='in_line')
            net.from_nx(g)

            mainFileNode = mainFile.split(".")[0] + ".txt"  # matches how files were renamed

            for node in net.nodes:
                if node['id'] == mainFileNode:
                    node['color'] = 'orange'
            output_file = pathDir + '/call_dependencies/calls.html'
            net.write_html(output_file)  # only writes the HTML
            print(f"\nDependencies analysis saved to: {output_file}")

            node_colors = ['orange' if node == mainFileNode else 'blue' for node in g.nodes()]
            nx.draw_circular(g, with_labels=True, node_color=node_colors)
            plt.draw()
            plt.savefig(pathDir+'/call_dependencies/'+'calls.png', dpi=300)
        else:
            print("Not a valid extension")
    else:
        print("Not a valid path")

if __name__ == "__main__":
    pathDir = input("Enter the directory path to be analysed: ")
    analyse_dependencies(pathDir)