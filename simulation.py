"""
Description of module...
"""
import math
import navigation as nav
import pandas as pd


# fill the initial state with N cars
N = 1
dt = 1/1000
speed_limit = 30e-6
stop_distance = 3.0e-6
free_distance = 5.0e-6
default_acceleration = 3.0e-6

TEMP_origin_node = 53028190
TEMP_dest_node = 53035698


def update_velocity(car):
    """

    :param car:
    :return:
    """


# def update_acceleration(car):
#     obstacles = nav.FrontView(car)
#     distances = obstacles.upcoming_distances()
    # acceleration =


def update_speed_factor(car):
    """
    handles logic for updating speed according to road curvature and car obstacles
    :param            car: dict
    :return: speed_factor: double
    """
    obstacles = nav.FrontView(car)
    angles = obstacles.upcoming_angles()
    distances = obstacles.upcoming_distances()
    obstacle_factor = car_obstacle_factor(distances[0])  # for later use with car obstacles
    speed_factor = road_curvature_factor(angles[0], distances[0])
    return speed_factor


def road_curvature_factor(theta, d):
    """
    calculates the speed factor (between 0 and 1) for road curvature
    :param         theta: double:  angle of road curvature ahead
    :return speed_factor: double:  factor by which to diminish speed
    """
    if theta == 0:
        curvature_factor = 1
    else:
        if (0 < d) and (d < free_distance):
            curvature_factor = math.log(d / (2 * theta / math.pi)) / math.log(free_distance / (2 * theta / math.pi))
        else:
            curvature_factor = 1
    return curvature_factor


def car_obstacle_factor(d):
    """
    function to update speed for a car in the front_view
    :param      d: double:   distance to car in front_view
    :return speed: double:  new speed
    """
    if (stop_distance < d) and (d < speed_limit):
        obstacle_factor = math.log(d / stop_distance) / math.log(free_distance / stop_distance)
    else:
        if d < stop_distance:
            obstacle_factor = 0
        else:
            obstacle_factor = 1
    return obstacle_factor


def init_culdesac_start_location(N):
    """
    initializes N cars into N culdesacs

    Parameters
    __________
    :param     N:   int

    Returns
    _______
    :return cars:   array:  [dict, ...]
    """
    culdesacs = nav.find_culdesacs()

    if N > len(culdesacs):
        raise ValueError('Number of cars greater than culdesacs to place them. '
                         'Choose a number less than {}'.format(len(culdesacs)))

    cars = []

    for i in range(N):
        start_node = culdesacs[i]
        position = nav.get_position_of_node(start_node)


        cars.append(
            {'position': position,
             'velocity': (0, 0),
             'acceleration': (0, 0),
             'front-view': {'distance-to-car': 10, 'distance-to-node': 0},
             'destination': TEMP_dest_node
             }
        )

    return cars


cars_dict = init_culdesac_start_location(N)
cars_df = pd.DataFrame(cars_dict)


