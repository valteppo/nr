import zipfile
import os
import urllib.request
import math
import random

def maintain_sde()-> None:
    """
    Assures up-to-date SDE.
    """
    dir = os.getcwd()
    try:
        os.mkdir(dir+"\\data")
    except FileExistsError:
        pass
    datadir = dir + "\\data\\"
    checksum = ""

    # if no files, download
    if not os.path.exists(datadir+"sde.zip"):
        urllib.request.urlretrieve("https://eve-static-data-export.s3-eu-west-1.amazonaws.com/tranquility/sde.zip", datadir+"\\sde.zip")
    if not os.path.exists(datadir+"checksum"):
        urllib.request.urlretrieve("https://eve-static-data-export.s3-eu-west-1.amazonaws.com/tranquility/checksum", datadir+"\\checksum")

    # verify checksum validity
    modified_since_seconds = os.path.getmtime(datadir+"checksum")
    if modified_since_seconds > 60*60*24: # only once a day
        checksum = open(datadir+"checksum").read()
        urllib.request.urlretrieve("https://eve-static-data-export.s3-eu-west-1.amazonaws.com/tranquility/checksum", datadir+"\\new_checksum")
        new_checksum = open(datadir+"\\new_checksum").read()
        if checksum != new_checksum:
            urllib.request.urlretrieve("https://eve-static-data-export.s3-eu-west-1.amazonaws.com/tranquility/sde.zip", datadir+"\\sde.zip")
        os.remove(datadir+"\\checksum")
        os.rename(datadir+"\\new_checksum", datadir+"\\checksum")

def extract_sde_solarsystem_data()-> list:
    """
    Wrangles system location data out of the SDE zip file.
    """
    # sub function
    def extract_system_data(data):
        start = data.find("center:") + len("center:")
        end = data.find("corridor:")
        xyz = list(filter(None, data[start:end].split("\n- ")))
        return [float(i) for i in xyz]

    # [system, region, x, y, z]
    systems = []

    with zipfile.ZipFile(os.getcwd()+"\\data\\sde.zip", "r") as handle:
        target = "sde/fsd/universe/eve/"
        tlen = len(target)
        for filename in handle.namelist():
            if filename[:tlen] == target:
                tokens = filename.split("/")
                if tokens[-1] == "solarsystem.staticdata":
                    with handle.open(filename) as file:
                        data = file.read().decode()
                        xyz = extract_system_data(data)
                        systems.append([tokens[6], tokens[4], xyz[0], xyz[1], xyz[2]])
    return systems

def system_filter(systems)-> list:
    """
    Filters out systems that aren't classic null-sec systems.
    """

    regions = ["Curse",
    "Great Wildlands",
    "Outer Ring",
    "Stain",
    "Syndicate",
    "Venal",
    "Branch",
    "Cache",
    "Catch",
    "Cloud Ring",
    "Cobalt Edge",
    "Deklein",
    "Delve",
    "Detorid",
    "Esoteria",
    "Etherium Reach",
    "Fade",
    "Feythabolis",
    "Fountain",
    "Geminate",
    "Immensea",
    "Impass",
    "Insmother",
    "Malpais",
    "Oasa",
    "Omist",
    "Outer Passage",
    "Paragon Soul",
    "Period Basis",
    "Perrigen Falls",
    "Providence",
    "Pure Blind",
    "Querious",
    "Scalding Pass",
    "Tenal",
    "Tenerifis",
    "The Kalevala Expanse",
    "The Spire",
    "Tribute",
    "Vale of the Silent",
    "Wicked Creek"]

    regions = [i.replace(" ", "").lower() for i in regions]
    out = []
    for system in systems:
        if system[1].replace(" ", "").lower() in regions:
            out.append(system)
    return out

def cubeify(systems, max_jump_distance_ly):
    """
    Splits universe to cubes for distance vector calculation.
    """
    ly = 9460730472580800
    reach = ly * max_jump_distance_ly
    cubes = {}
    for system in systems:
        x = math.floor(system[2] / reach)
        y = math.floor(system[3] / reach)
        z = math.floor(system[4] / reach)
        s = f"x{x};y{y};z{z}"
        if s not in cubes:
            cubes[s] = [system]
        else:
            a = cubes[s]
            a.append(system)
            cubes[s] = a
    return cubes

def vector_lenght(system1, system2)-> float:
    i = system2[2]-system1[2]
    j = system2[3]-system1[3]
    k = system2[4]-system1[4]
    return math.sqrt(i*i + j*j + k*k)

def assign_jumps(cubed_map, max_jump_distance_ly)-> dict:
    """
    Go through cube in mapped cubes. List neighbouring cubes. Add systems from cube and neighbouring cubes
    to check list. Go through systems in cube, calculate distance to systems in reach from check list.
    If in range, add to connections dict.

    Return dict {system: [[connection system, region of conn system, distance in ly], ... ]}
    """
    ly = 9460730472580800
    reach = ly * max_jump_distance_ly
    connections = {}
    for key in cubed_map:
        cube = cubed_map[key]

        # Current cube address
        x, y, z = cube[0][2], cube[0][3], cube[0][4]
        x = math.floor(x/reach)
        y = math.floor(y/reach)
        z = math.floor(z/reach)

        # Get systems from current cube and all neighbouring cubes.
        ijk = [[i, j, k] for i in range(-1, 2) for j in range(-1, 2) for k in range(-1, 2)]
        systems_to_check = []
        for modifier in ijk:
            if f"x{x+modifier[0]};y{y+modifier[1]};z{z+modifier[2]}" not in cubed_map:
                continue
            surroundings = cubed_map[f"x{x+modifier[0]};y{y+modifier[1]};z{z+modifier[2]}"]
            for system in surroundings:
                systems_to_check.append(system)
        
        # Go through systems in current active cube and calculate distances to near-by systems
        for system in cube:
            for target in systems_to_check:
                if system[0] == target[0]:
                    continue
                distance = vector_lenght(system, target)
                if distance/ly < max_jump_distance_ly: # in range
                    if system[0] not in connections:
                        connections[system[0]] = [target[0], target[1], distance/ly]
                    else:
                        a = connections[system[0]]
                        a.append([target[0], target[1], distance/ly])
                        connections[system[0]] = a
    return connections

def method_one(target_n, mapped, systems)-> list:
    """
    Rolls 2 holes randomly until systems are in jump range. Records amount of rolls needed per connection.
    Repeats to target amount.
    Returns [numer of rolls for connection, ..., ...]
    """
    res = []
    for n in range(1, target_n+1):
        connected = False
        rolls = 0
        while not connected:
            rolls += 1
            system_a = random.choice(systems)
            system_b = random.choice(systems)
            if system_b[0] in mapped[system_a[0]]:
                res.append(rolls)
                connected = True
    return res

def method_two(target_n, mapped, systems)-> list:
    """
    Roll 2 holes. Keep the one with higher amount of connections, roll the other.
    Repeats to target amount.
    Returns [numer of rolls for connection, ..., ...]
    """
    res = []
    for n in range(1, target_n+1):
        connected = False
        rolls = 1
        system_a = random.choice(systems)
        system_b = random.choice(systems)
        while not connected:
            rolls += 1
            if system_b[0] in mapped[system_a[0]]:
                res.append(rolls)
                connected = True
            elif len(mapped[system_b[0]]) < len(mapped[system_a[0]]):
                system_a = system_b
            system_b = random.choice(systems)
    return res

def main():
    jump_distance = 8
    simulate_connections = 5001

    maintain_sde()
    systems = system_filter(extract_sde_solarsystem_data())
    cubed = cubeify(systems, jump_distance)
    mapped = assign_jumps(cubed, jump_distance)
    one = method_one(simulate_connections, mapped, systems)
    two = method_two(simulate_connections, mapped, systems)

    av_one = 0
    for i in one:
        av_one += i
    av_one = av_one / simulate_connections

    av_two = 0
    for i in two:
        av_two += i
    av_two = av_two / simulate_connections

    one.sort()
    two.sort()
    print(f"method one: average: {av_one}, median: {one[simulate_connections//2]}")
    print(f"method two: average: {av_two}, median: {two[simulate_connections//2]}")

main()
