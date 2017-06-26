#
import sys, os, re
import json
# from pprint import pprint

# Convert json content in a file to a python data structure
def file2json(file):
    with open(file) as f:
        j = json.load(f)
    return j

# Strip out the unique trailing ids added to pod names
def filter_pod_name(name):
    words = name.split('-')
    return '-'.join(words[:-2])

# Remove AX env vars
def filter_vars(vars):
    res = []
    for var in vars:
        if var['name'].startswith('AX_'):
            continue
        res.append(var)
    return res

# Remove non-user volumes
def filter_vols(vols):
    ignore_vols = [
        'bin-nothing',
        'artifacts-scratch',
        'static-bins',
        'docker-socket-file',
        'annotations',
        'applet'
    ]

    res = []
    for vol in vols:
        if vol['name'] in ignore_vols:
            continue
        if vol['name'].startswith('default-token-'):
            continue
        res.append(vol)
    return res

# Only keep the attributes that we are interested in.
def filter_containers(containers):
    res = []
    for container in containers:
        c = {
            'name': container['name'],
            'image': container['image'],
            'command': container['command'],
            'env': filter_vars(container['env']),
            'resources': container['resources'],
            'volumeMounts': filter_vols(container['volumeMounts'])
        }
        res.append(c)
    return res

# Remove the AX pods.
def filter_pods(pods):
    res = []
    for pod in pods:
        if pod['metadata']['name'].startswith('axam-deployment-'):
            continue
        p = {
            'name': filter_pod_name(pod['metadata']['name']),
            'containers': filter_containers(pod['spec']['containers'])
        }
        res.append(p)
    return res

# Given a list of dicts, create a dictionary indexed by the value of the specified key.
def dictify_by_key_value(lst, key):
    res = {}
    for i in range(len(lst)):
        res[lst[i][key]] = lst[i]
    return res

# Differences between volume mounts.
def diff_volume_mounts(vs1, vs2):
    d1 = dictify_by_key_value(vs1, 'name')
    d2 = dictify_by_key_value(vs2, 'name')
    names = list(set(list(d1) + list(d2)))

    res = []
    for name in names:
        if not name in d1:
            t = {
                'name': name,
                '_status': (None, '')
            }
        elif not name in d2:
            t = {
                'name': name,
                '_status': ('', None)
            }
        else:
            t = {
                'name': name,
                'mountPath': (d1[name]['mountPath'] if name in d1 else None, d2[name]['mountPath'] if name in d2 else None )
            }
        res.append(t)
    return res
        
# Differences between env vars.
def diff_vars(vs1, vs2):
    d1 = dictify_by_key_value(vs1, 'name')
    d2 = dictify_by_key_value(vs2, 'name')
    names = list(set(list(d1) + list(d2)))

    res = []
    for name in names:
        t = {
            'name': name,
            'value': (d1[name]['value'] if name in d1 else None, d2[name]['value'] if name in d2 else None )
        }
        res.append(t)
    return res

# Differences between containers.
def diff_containers(cs1, cs2):
    d1 = dictify_by_key_value(cs1, 'name')
    d2 = dictify_by_key_value(cs2, 'name')
    names = list(set(list(d1) + list(d2)))

    res = []
    for name in names:
        if not name in d1 and not name in d2:
            continue;
        if not name in d1:
            t = {
                'name': name,
                '_status': (None, '')
            }
        elif not name in d2:
            t = {
                'name': name,
                '_status': ('', None)
            }
        else:
            t = {
                'name': name,
            }
            c1 = d1[name]
            c2 = d2[name]
            key = 'image'
            if c1[key] != c2[key]:
                t[key] = (c1[key], c2[key])
            key = 'command'
            if c1[key] != c2[key]:
                t[key] = (c1[key], c2[key])
            key = 'env'
            if c1[key] != c2[key]:
                t[key] = diff_vars(c1[key], c2[key])
            key = 'resources'
            if c1[key] != c2[key]:
                t[key] = (c1[key]['requests'], c2[key]['requests'])
            key = 'volumeMounts'
            if c1[key] != c2[key]:
                t[key] = diff_volume_mounts(c1[key], c2[key])
        res.append(t)
    return res


# Differences in attributes between  two pods.
def diff_pods(ps1, ps2):
    d1 = dictify_by_key_value(ps1, 'name')
    d2 = dictify_by_key_value(ps2, 'name')
    names = list(set(list(d1) + list(d2)))

    res = []
    for name in names:
        if not name in d1 and not name in d2:
            continue;
        if not name in d1:
            p = {
                'name': name,
                '_status': (None, '')
            }
        elif not name in d2:
            p = {
                'name': name,
                '_status': ('', None)
            }
        else:
            p = {
                'name': name,
                'containers': diff_containers(d1[name]['containers'], d2[name]['containers'])
            }
        res.append(p)

    return res

# Compare two name spaces
def compare_ns(file1, file2):
    j1 = file2json(file1)
    j2 = file2json(file2)

    ps1 = filter_pods(j1['items'])
    ps2 = filter_pods(j2['items'])

    diff = diff_pods(ps1, ps2)
    return diff

# Print a report of the diffs between two name spaces
def print_diff_ns(file1, file2):
    diff = compare_ns(file1, file2)
    
    format = "%-30s %-40s %-40s"
    print(format % ("applications", file1, file2))
    for pod in diff:
        if '_status' in pod:
            print(format % (" "*2 + 'pod:'+pod['name'], pod['_status'][0], pod['_status'][1]))
            continue
        else:
            print(format % (" "*2 + 'pod:'+pod['name'], "", ""))
        for container in pod['containers']:
            key = '_status'
            if 'key' in container:
                print(format % (" "*4 + 'container:' + container['name'], container[key][0], container[key][1]))
                continue
            else:
                print(format % (" "*4 + 'container:' + container['name'], "", ""))

            key = 'image'
            if key in container:
                print(format % (" "*6 + key, container[key][0], container[key][1]))

            key = 'command'
            if key in container:
                print(format % (" "*6 + key, container[key][0], container[key][1]))

            key = 'env'
            if key in container:
                print(format % (" "*6 + key, "", ""))
                for var in container[key]:
                    print(format % (" "*8 + var['name'], var['value'][0], var['value'][1]))

            key = 'resources'
            if key in container:
                print(format % (" "*6 + key, container[key][0], container[key][1]))

            key = 'volumeMounts'
            if key in container:
                print(format % (" "*6 + key, "", ""))
                for volume in container[key]:
                    print(format % (" "*8 + volume['name'], volume['mountPath'][0], volume['mountPath'][1]))

#
#
#
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('usage: %s file1 file2' % (sys.argv[0]))
        sys.exit(1)

    file1 = sys.argv[1]
    file2 = sys.argv[2]
    
    print_diff_ns(file1, file2)

