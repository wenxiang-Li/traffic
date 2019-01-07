"""
This module is the only one capable of referencing the map G
and thus contains methods for updating car position and finding path to car destination;
also contains methods for locating cars and intersections in the front_view
and calculating the curvature of the bend in the road for speed adjustments
"""
import models
import networkx as nx
import numpy as np
import osmnx as ox


G = ox.load_graphml('piedmont.graphml')
# G = ox.load_graphml('sanfrancisco.graphml')
# G = ox.load_graphml('lowermanhattan.graphml')
G = ox.project_graph(G)


class FrontView:
    def __init__(self, car, look_ahead_nodes=3):
        """
        take a car Series and determines the obstacles it faces in its frontal view

        :param              car: Series row of the main dataframe
        :param look_ahead_nodes: int
        """
        self.look_ahead_nodes = look_ahead_nodes
        self.car = car
        self.position = car['x'], car['y']
        self.view = self.determine_view()
        self.angles = models.get_angles(self.view)

    def determine_view(self):
        """
        this method handles the exception where the path is shorter than look_ahead_nodes

        :return view: list or bool: list of nodes immediately ahead of the car or False if end of route
        """
        if self.car['xpath'] and self.car['ypath']:
            x, y = self.car['xpath'][:self.look_ahead_nodes], self.car['ypath'][:self.look_ahead_nodes]
            return [(x[i], y[i]) for i in range(len(x))]
        else:
            return False

    def distance_to_car(self, cars):
        """
        dispatches a car Series into another nav function and retrieves the distance to a car obstacle if there is one

        :param      cars: Dataframe of cars
        :return distance:
        """
        return car_obstacles(self, cars)

    def distance_to_light(self, lights):
        """
        dispatches a car Series into another nav function and retrieves the distance to a red light if there is one

        :param    lights: Dataframe of lights
        :return distance:
        """
        return light_obstacles(self, lights)

    def distance_to_node(self):
        """
        Determines the distance to the most immediate node

        :return distance: double
        """
        next_node = np.array(self.upcoming_node_position())
        distance_vector = next_node - self.position
        distance = models.magnitude(distance_vector)
        return distance

    def upcoming_node_position(self):
        """
        Determines the coordinates of the next node in view

        :return view: tuple: returns upcoming node coords in the path
        """
        if self.view:
            if self.crossed_node_event():
                if len(self.view) >= 2:
                    return self.view[1]
                else:
                    return get_position_of_node(self.car['destination'])
            else:
                return self.view[0]
        else:
            # end of route
            return get_position_of_node(self.car['destination'])

    def crossed_node_event(self):
        """
        Determines if the car has crossed a node, and advises simulation to change
        its velocity vector accordingly

        :return bool: True if the car is passing a node, False otherwise
        """
        car_near_xnode = np.isclose(self.view[0][0], self.car['x'], rtol=1.0e-6)
        car_near_ynode = np.isclose(self.view[0][1], self.car['y'], rtol=1.0e-6)

        if car_near_xnode and car_near_ynode:
            return True
        else:
            return False

    def end_of_route(self, stop_distance):
        """
        Determines if the car has reached the end of the route

        :param stop_distance: double or int from simulation.py
        :return         bool: False if not, True if car is at the end of its root
        """
        xdest, ydest = get_position_of_node(self.car['destination'])
        car_near_xdest = np.isclose(xdest, self.car['x'], atol=stop_distance)
        car_near_ydest = np.isclose(ydest, self.car['y'], atol=stop_distance)

        if car_near_xdest and car_near_ydest:
            return True
        else:
            return False


class StateView:
    def __init__(self, axis, car_index, cars, lights):
        self.axis = axis
        self.cars = cars
        self.lights = lights
        self.index = car_index
        self.car = cars.loc[self.index]
        self.route = np.array(self.car['route'])
        self.eta = eta(self.car, self.lights)
        self.max_cars = 10  # the number of cars in a bin for the bin to be considered 'congested'
        self.speed_limit = 250

    def determine_state(self):
        """
        this method gathers information about the car's route, and determines which state the car is in

        :return state: list
        """
        if self.route[0] != self.car['destination']:
            # get light IDs in the route
            light_locs = self.get_lights_in_route()
            # get congested bins
            traffic_bins = self.get_traffic_bins()

            if light_locs or traffic_bins:
                if light_locs:
                    # re-route around light with longest switch-time (last light in array due to sorting)
                    light_node = self.lights.loc[light_locs[-1]]['node']

                    """
                    Determine the reroute_node as the node in the route directly before the light obstacle
                    """
                    # TODO: this node is not ideal when it is not an intersection. Handle this case
                    reroute_node = self.route[np.where(self.route == light_node)[0][0] - 1]

                    # determine in which direction to reroute
                    possible_directions = np.array([dot for dot in G[reroute_node].__iter__()])
                    indices = [np.where(node == self.route) for node in possible_directions]
                    directions = np.delete(possible_directions, indices)


                    return 'not finished'
            else:
                # there are no obstacles along the current route (STATE 4)
                return [0, 0, 0, 1, 0, 0]
        else:
            # the car has arrived at the destination (STATE 6)
            state = [0, 0, 0, 0, 0, 1]
            return state

    def get_lights_in_route(self):
        """
        this method returns the IDs of the traffic lights anywhere along the route

        :return light_locs: a list of light IDs
        """
        light_locs = np.array([(node == self.lights['node']).tolist().index(True) for node in self.route
                      if (node == self.lights['node']).any()])

        # sort lights by switch-time
        light_locs = [id for id in self.lights['switch-time'].argsort() if (id == light_locs).any()]

        return light_locs

    def get_traffic_bins(self):
        """
        this method returns the (xbin, ybin) pair of a bins which are considered to be congested with traffic

        :return traffic_bins: list: list of tuples
        """
        traffic_bins = []
        xbins, ybins = self.get_bins_in_route()
        for xbin, ybin in zip(xbins, ybins):
            population_of_bin = 0
            for i, (cars_xbin, cars_ybin) in enumerate(zip(self.cars['xbin'], self.cars['ybin'])):
                if (xbin, ybin) == (cars_xbin, cars_ybin):
                    population_of_bin += 1

            if population_of_bin > self.max_cars:
                traffic_bins.append((xbin, ybin))
        return traffic_bins

    def get_bins_in_route(self):
        """
        this method parses the route and returns a list of xbins and ybins through which the route passes

        :return xbins, ybins
        """
        xbins, ybins = np.arange(self.axis[0], self.axis[1], 200), np.arange(self.axis[2], self.axis[3], 200)
        x_inds, y_inds = [], []
        for node in self.route:
            x, y = get_position_of_node(node)
            x_inds.append(np.digitize(x, xbins))
            y_inds.append(np.digitize(y, ybins))

        x_inds, y_inds = np.array(x_inds), np.array(y_inds)

        # remove double-counted bins from result
        xbins, ybins = [], []
        for i in range(len(x_inds)):
            if i < len(x_inds) - 1:
                if (x_inds[i] == x_inds[i + 1]) and (y_inds[i] == y_inds[i + 1]):
                    continue
                else:
                    xbins.append(x_inds[i])
                    ybins.append(y_inds[i])

        xbins.append(x_inds[-1])
        ybins.append(y_inds[-1])

        return xbins, ybins


def car_obstacles(frontview, cars):
    """
    Determines if there are any other_cars within the car's bin and then

    Parameters
    __________
    :param frontview:    object: FrontView object
    :param      cars: dataframe:

    Returns
    _______
    :return distance: list: double or False (returns False if no car obstacle found)
    """
    x_space, y_space = models.upcoming_linspace(frontview)
    if x_space.any() and y_space.any():
        other_cars = cars.drop(frontview.car.name)
        obstacles = (frontview.car['xbin'] == other_cars['xbin']) & (frontview.car['ybin'] == other_cars['ybin'])
        if obstacles.any():
            nearby_cars = other_cars[obstacles]
            for car in nearby_cars.iterrows():
                car_within_xlinspace = np.isclose(x_space, car[1]['x'], rtol=1.0e-6).any()
                car_within_ylinspace = np.isclose(y_space, car[1]['y'], rtol=1.0e-6).any()

                if car_within_xlinspace and car_within_ylinspace:
                    first_x, first_y = car[1]['x'], car[1]['y']
                    vector = (first_x - frontview.car['x'], first_y - frontview.car['y'])
                    distance = models.magnitude(vector)
                    return distance
                else:
                    return False
        else:
            return False
    else:
        return False


def light_obstacles(frontview, lights):
    """
    Determines the distance to red traffic lights. If light is green, returns False

    Parameters
    __________
    :param  frontview:    object: FrontView object
    :param     lights: dataframe:

    Returns
    _______
    :return distance: list: double for False (returns False if no red light is found)
    """
    x_space, y_space = models.upcoming_linspace(frontview)
    if x_space.any() and y_space.any():
        obstacles = (frontview.car['xbin'] == lights['xbin']) & (frontview.car['ybin'] == lights['ybin'])
        if obstacles.any():
            nearby_lights = lights[obstacles]
            for light in nearby_lights.iterrows():
                light_within_xlinspace = np.isclose(x_space, light[1]['x'], rtol=1.0e-6).any()
                light_within_ylinspace = np.isclose(y_space, light[1]['y'], rtol=1.0e-6).any()

                if light_within_xlinspace and light_within_ylinspace:
                    car_vector = [light[1]['x'] - frontview.car['x'], light[1]['y'] - frontview.car['y']]
                    face_values = light[1]['go-values']
                    face_vectors = [(light[1]['out-xvectors'][i], light[1]['out-yvectors'][i])
                                    for i in range(light[1]['degree'])]

                    for value, vector in zip(face_values, face_vectors):
                        if not value and models.determine_parallel_vectors(car_vector, vector):
                            distance = models.magnitude(car_vector)
                            return distance
                        else:
                            continue
                else:
                    return False
        else:
            return False
    else:
        return False


def determine_pedigree(node_id):
    """
     each traffic light has a list of vectors, pointing in the direction of the road a light color should influence

     :param  node_id:    int
     :return vectors:   list: list of vectors pointing from the intersection to the nearest point on the out roads
     """
    # TODO: use the native AtlasView object in NetworkX to determine the pedigree
    position = get_position_of_node(node_id)

    left_edges = []
    right_edges = []
    for edge in G.edges():
        if edge[0] == node_id:
            left_edges.append(edge)
        if edge[1] == node_id:
            right_edges.append(edge)

    for left in left_edges:
        for i, right in enumerate(right_edges):
            if (left[1] == right[0]) and (right[1] == left[0]):
                right_edges.pop(i)

    intersection_edges = left_edges + right_edges

    out_nodes = []
    for edge in intersection_edges:
        if edge[0] == node_id:
            out_nodes.append(edge[1])
        else:
            out_nodes.append(edge[0])

    vectors = []
    for node in out_nodes:
        try:
            point = lines_to_node(node_id, node)[0][1]
        except IndexError:
            continue
        vectors.append((point[0] - position[0], point[1] - position[1]))

    return vectors


def find_culdesacs():
    """
    culdesacs are nodes with only one edge connection and which are not on the boundary of the OpenStreetMap

    :return culdesacs: list of node IDs
    """
    culdesacs = [key for key, value in G.graph['streets_per_node'].items() if value == 1]
    return culdesacs


def find_traffic_lights(prescale=10):
    """
    traffic lights are nodes in the graph which have degree > 3

    :return light_intersections: a list of node IDs suitable for traffic lights
    """
    light_intersections = []
    for i, node in enumerate(G.degree()):
        if (node[1] > 3) and not (i % prescale):
            light_intersections.append(node)

    return light_intersections


def find_nodes(n):
    """
    returns n node IDs from the networkx graph

    :param      n: int
    :return nodes: list
    """
    nodes = []
    for node in G.nodes():
        nodes.append(node)
    return nodes[:n]


def get_position_of_node(node):
    """
    Get latitude and longitude given node ID

    :param node:      graphml node ID
    :return position: array:    [latitude, longitude]
    """
    # note that the x and y coordinates of the G.nodes are flipped
    # this is possibly an issue with the omnx G.load_graphml method
    # a correction is to make the position tuple be (y, x) as below
    position = np.array([G.nodes[node]['x'], G.nodes[node]['y']])
    return position


def get_init_path(origin, destination):
    """
    compiles a list of tuples which represents a route

    Parameters
    __________
    :param      origin: int:    node ID
    :param destination: int:    node ID

    Returns
    _______
    :return path: list where each entry is a tuple of tuples
    """
    lines = shortest_path_lines_nx(origin, destination)
    path = models.path_decompiler(lines)
    return path


def get_route(origin, destination):
    """
    acquires the typical node-based route list from NetworkX with weight=length

    :param      origin: node ID
    :param destination: node ID
    :return:     route: list of intersection nodes
    """
    return nx.shortest_path(G, origin, destination, weight='length')


def eta(car, lights, speed_limit=250):
    """
    calculates the ETA by considering traffic lights, car traffic (in future versions), and distances

    :param            car: Series
    :param         lights: DataFrame
    :param    speed_limit: int
    :return:    path_time: double
    """
    route = car['route']

    route_length = sum([G.get_edge_data(route[i], route[i + 1])[0]['length']
                        for i in range(len(route) - 1)])

    eta_from_distance = route_length / speed_limit  # does not account for road curvature or hard stops at intersections

    light_locs = [(node == lights['node']).tolist().index(True) for node in route if (node == lights['node']).any()]

    # let the expected wait time for all lights found in the route be half the sum of the times
    expected_wait = sum([lights.loc[index]['switch-time'] for index in light_locs]) / 2
    path_time = eta_from_distance + expected_wait
    return path_time


def build_new_route(route, reroute_node, direction):
    """
    this function builds a new route for a car based on the original route given that it would like to turn off
    the original route at the reroute_node

    :param        route: list: the original Dijkstra's shortest path
    :param reroute_node:  int: the node at which the car would like to depart the original path
    :param    direction:  int: the next node after reroute_node in the direction of the departure

    :return:  new_route: list: the new route based on the new direction
    """
    # TODO: make this function more sophisticated so that it doesn't find bad routes
    reroute_index = route.index(reroute_node)
    new_route = route[:reroute_index + 1]
    new_route.append(direction)

    # get the coordinate positions of the next three nodes in the original route
    next_nodes_pos = []
    for node in route[reroute_index + 1:reroute_index + 4]:
        x, y = get_position_of_node(node)
        next_nodes_pos.append((x, y))

    returned = False
    i = 0
    while not returned:
        i += 1
        out_from_direction = [dot for dot in G[direction].__iter__()]
        out_from_direction.pop(out_from_direction.index(reroute_node))

        # Populate a list of the sums of the distances to the next
        # three nodes in the original route, for each potential new node
        sum_three_node_dist = []
        for node in out_from_direction:
            twice_out = [dot for dot in G[node].__iter__()]
            np_twice = np.array(twice_out)
            if (direction == np_twice).any():
                twice_out.pop(twice_out.index(direction))
            if not twice_out:
                sum_three_node_dist.append('disqualified')

            distances = []
            for compare_node in next_nodes_pos:
                potential_node_pos = get_position_of_node(node)
                distances.append(np.linalg.norm(compare_node - potential_node_pos))
            sum_three_node_dist.append(sum(distances))

        sum_three_node_dist, route = np.array(sum_three_node_dist), np.array(route)
        next_node = out_from_direction[sum_three_node_dist.argsort()[0]]
        print(i, next_node)
        new_route.append(next_node)
        if (next_node == route[reroute_index + 1:]).any():
            start_at_index = route.tolist().index(next_node)
            for node in route[start_at_index + 1:]:
                new_route.append(node)
            returned = True
        else:
            reroute_node = direction
            direction = next_node

    lines = []
    for i in range(len(new_route)):
        if i < len(new_route) - 1:
            lines.append(shortest_path_lines_nx(new_route[i], new_route[i + 1]))

    new_path = []
    for geometry in lines:
        for point in geometry[0]:
            new_path.append(point)

    new_clean_path = models.new_route_decompiler(new_path)
    new_xpath, new_ypath = [point[0] for point in new_clean_path], [point[1] for point in new_clean_path]
    return new_route, new_xpath, new_ypath


def lines_to_node(origin, destination):
    """
    return the points of all nodes in the route, including the minor nodes which make up line geometry

    :param      origin: int
    :param destination: int
    :return      lines: list
    """

    route = nx.shortest_path(G, origin, destination, weight='length')

    # find the route lines
    edge_nodes = list(zip(route[:-1], route[1:]))
    lines = []
    for u, v in edge_nodes:
        # if there are parallel edges, select the shortest in length
        data = min(G.get_edge_data(u, v).values(), key=lambda x: x['length'])

        # if it has a geometry attribute (ie, a list of line segments)
        if 'geometry' in data:
            # add them to the list of lines to plot
            xs, ys = data['geometry'].xy
            lines.append(list(zip(xs, ys)))
        else:
            # if it doesn't have a geometry attribute, the edge is a straight
            # line from node to node
            x1 = G.nodes[u]['x']
            y1 = G.nodes[u]['y']
            x2 = G.nodes[v]['x']
            y2 = G.nodes[v]['y']
            line = ((x1, y1), (x2, y2))
            lines.append(line)

    return lines


def shortest_path_lines_nx(origin, destination):
    """
    uses the default shortest path algorithm available through networkx

    Parameters
    __________
    :param      origin: int:    node ID
    :param destination: int:    node ID

    Returns
    _______
    :return lines: list:
        [(double, double), ...]:   each tuple represents the bend-point in a straight road
    """

    route = nx.shortest_path(G, origin, destination, weight='length')

    # find the route lines
    edge_nodes = list(zip(route[:-1], route[1:]))
    lines = []
    for u, v in edge_nodes:
        # if there are parallel edges, select the shortest in length
        data = min(G.get_edge_data(u, v).values(), key=lambda x: x['length'])

        # if it has a geometry attribute (ie, a list of line segments)
        if 'geometry' in data:
            # add them to the list of lines to plot
            xs, ys = data['geometry'].xy
            lines.append(list(zip(xs, ys)))
        else:
            # if it doesn't have a geometry attribute, the edge is a straight
            # line from node to node
            x1 = G.nodes[u]['x']
            y1 = G.nodes[u]['y']
            x2 = G.nodes[v]['x']
            y2 = G.nodes[v]['y']
            line = ((x1, y1), (x2, y2))
            lines.append(line)

    return lines
