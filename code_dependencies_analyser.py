import matplotlib.pyplot as plt
import os
import glob
from fnmatch import fnmatch
import shutil
import networkx as nx
from pyvis.network import Network

def analyse_dependencies(pathDir, fileType='py'):
    #Load all files and append to a list
    if os.path.exists(pathDir):
        if fileType in ['py','txt','m']: 
            fileType = "*.{}".format(fileType)
            try:
                os.mkdir(pathDir+"/Call_Dependencies")
            except:
                print("Directory exists")

            for path, subdirs, files in os.walk(pathDir):
                for name in files:
                    if fnmatch(name, fileType):
                        try:
                            shutil.copy(os.path.join(path, name),pathDir+"/Call_Dependencies/"+name)
                            # print(os.path.join(path, name))
                            prefix = name.split(".")
                            os.rename(pathDir+"/Call_Dependencies/"+name,pathDir+"/Call_Dependencies/"+prefix[0]+".txt")
                        except:
                            continue

            paths = glob.glob(pathDir+"/Call_Dependencies/*.txt*")
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
            print(functions)
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
                    print(fName)
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
            for node in net.nodes:
                if node['id'] == 'main.txt':
                    node['color'] = 'orange'
            net.show(pathDir+'/Call_Dependencies/'+'calls.html')


            node_colors = ['orange' if node == 'main.txt' else 'blue' for node in g.nodes()]
            nx.draw_circular(g, with_labels=True, node_color=node_colors)
            plt.draw()
            plt.savefig(pathDir+'/Call_Dependencies/'+'calls.png', dpi=300)
        else:
            print("Not a valid extension")
    else:
        print("Not a valid path")

if __name__ == "__main__":
    pathDir = input("Enter the directory path to be analysed: ")
    analyse_dependencies(pathDir)