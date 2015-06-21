import pickle

from worldengine.biome import *
from worldengine.basic_map_operations import *
import worldengine.protobuf.World_pb2 as Protobuf
from worldengine.step import Step
import math

execfile('worldengine/version.py')


def cubic_interpolate(p0, p1, p2, p3, t):
    """
    :param p0: value preceding (corresponding to t=-1)
    :param p1: value preceding (corresponding to t=0)
    :param p2: value following (corresponding to t=1)
    :param p3: value following (corresponding to t=2)
    :param t: between 0 and 1 indicates how close to p1 or p2 the value ie
    :return:
    """
    return p1 + \
        (-0.5 * p0 + 0.5 * p2) * t + \
        (p0 - 2.5 * p1 + 2.0 * p2 - 0.5 * p3) * t * t + \
        (-0.5 * p0 + 1.5 * p1 - 1.5 * p2 + 0.5 * p3) * t * t * t


def bicubic_interpolate(p, tx, ty):
    tmp0 = cubic_interpolate(p[0][0], p[0][1], p[0][2], p[0][3], ty)
    tmp1 = cubic_interpolate(p[1][0], p[1][1], p[1][2], p[1][3], ty)
    tmp2 = cubic_interpolate(p[2][0], p[2][1], p[2][2], p[2][3], ty)
    tmp3 = cubic_interpolate(p[3][0], p[3][1], p[3][2], p[3][3], ty)
    return cubic_interpolate(tmp0, tmp1, tmp2, tmp3, tx)


def rescale_float_matrix(old_matrix, new_width, new_height):
    old_width = len(old_matrix[0])
    old_height = len(old_matrix)
    rescaled_matrix = [[0.0 for x in range(new_width)] for y in range(new_height)]
    for y in range(new_height):
        print("rescaling %i" % y)
        for x in range(new_width):
            p = [[0.0 for x in range(4)] for y in range(4)]
            old_x = float(x) * old_width / new_width
            old_y = float(y) * old_height / new_height
            px1 = math.floor(old_x)
            py1 = math.floor(old_y)
            for dy in range(-1, 3):
                for dx in range(-1, 3):
                    p[1 + dy][1 + dx] = old_matrix[(y+dy)%old_height][(x+dx)%old_width]
            rescaled_matrix[y][x] = bicubic_interpolate(p, old_x - px1, old_y - py1)
    return rescaled_matrix


def rescale_int_matrix(old_matrix, new_width, new_height):
    old_width = len(old_matrix[0])
    old_height = len(old_matrix)
    rescaled_matrix = [[0 for x in range(new_width)] for y in range(new_height)]
    for y in range(new_height):
        print("rescaling %i" % y)
        for x in range(new_width):
            p = [[0.0 for x in range(4)] for y in range(4)]
            old_x = float(x) * old_width / new_width
            old_y = float(y) * old_height / new_height
            px1 = math.floor(old_x)
            py1 = math.floor(old_y)
            for dy in range(-1, 3):
                for dx in range(-1, 3):
                    p[1 + dy][1 + dx] = float(old_matrix[(y+dy)%old_height][(x+dx)%old_width])
            rescaled_matrix[y][x] = int(bicubic_interpolate(p, old_x - px1, old_y - py1))
    return rescaled_matrix


class World(object):
    """A world composed by name, dimensions and all the characteristics of
    each cell.
    """

    def __init__(self, name, width, height, seed, num_plates, ocean_level,
                 step):
        self.name = name
        self.width = width
        self.height = height
        self.seed = seed
        self.n_plates = num_plates
        self.ocean_level = ocean_level
        self.step = step

    #
    # General methods
    #

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    #
    # Serialization/Unserialization
    #

    @classmethod
    def from_pickle_file(cls, filename):
        with open(filename, "rb") as f:
            return pickle.load(f)

    def to_pickle_file(self, filename):
        with open(filename, "wb") as f:
            pickle.dump(self, f, pickle.HIGHEST_PROTOCOL)

    @classmethod
    def from_dict(cls, dict):
        instance = World(dict['name'], dict['width'], dict['height'])
        for k in dict:
            instance.__dict__[k] = dict[k]
        return instance

    def protobuf_serialize(self):
        p_world = self._to_protobuf_world()
        return p_world.SerializeToString()

    def protobuf_to_file(self, filename):
        with open(filename, "wb") as f:
            f.write(self.protobuf_serialize())

    @staticmethod
    def open_protobuf(filename):
        with open(filename, "rb") as f:
            content = f.read()
            return World.protobuf_unserialize(content)

    @classmethod
    def protobuf_unserialize(cls, serialized):
        p_world = Protobuf.World()
        p_world.ParseFromString(serialized)
        return World._from_protobuf_world(p_world)

    @staticmethod
    def _to_protobuf_matrix(matrix, p_matrix, transformation=None):
        for row in matrix:
            p_row = p_matrix.rows.add()
            for cell in row:
                value = cell
                if transformation:
                    value = transformation(value)
                p_row.cells.append(value)

    @staticmethod
    def _to_protobuf_quantiles(quantiles, p_quantiles):
        for k in quantiles:
            entry = p_quantiles.add()
            v = quantiles[k]
            entry.key = int(k)
            entry.value = v

    @staticmethod
    def _to_protobuf_matrix_with_quantiles(matrix, p_matrix):
        World._to_protobuf_quantiles(matrix['quantiles'], p_matrix.quantiles)
        World._to_protobuf_matrix(matrix['data'], p_matrix)

    @staticmethod
    def _from_protobuf_matrix(p_matrix, transformation=None):
        matrix = []
        for p_row in p_matrix.rows:
            row = []
            for p_cell in p_row.cells:
                value = p_cell
                if transformation:
                    value = transformation(value)
                row.append(value)
            matrix.append(row)
        return matrix

    @staticmethod
    def _from_protobuf_quantiles(p_quantiles):
        quantiles = {}
        for p_quantile in p_quantiles:
            quantiles[str(p_quantile.key)] = p_quantile.value
        return quantiles

    @staticmethod
    def _from_protobuf_matrix_with_quantiles(p_matrix):
        matrix = {}
        matrix['data'] = World._from_protobuf_matrix(p_matrix)
        matrix['quantiles'] = World._from_protobuf_quantiles(
            p_matrix.quantiles)
        return matrix

    @staticmethod
    def worldengine_tag():
        return ord('W') * (256 ** 3) + ord('o') * (256 ** 2) + \
            ord('e') * (256 ** 1) + ord('n')


    def __version_hashcode__(self):
        parts = __version__.split('.')
        return int(parts[0])*(256**3) + int(parts[1])*(256**2) + int(parts[2])*(256**1)

    def _to_protobuf_world(self):
        p_world = Protobuf.World()

        p_world.worldengine_tag = World.worldengine_tag()
        p_world.worldengine_version = self.__version_hashcode__()

        p_world.name = self.name
        p_world.width = self.width
        p_world.height = self.height

        p_world.generationData.seed = self.seed
        p_world.generationData.n_plates = self.n_plates
        p_world.generationData.ocean_level = self.ocean_level
        p_world.generationData.step = self.step.name

        # Elevation
        self._to_protobuf_matrix(self.elevation['data'], p_world.heightMapData)
        p_world.heightMapTh_sea = self.elevation['thresholds'][0][1]
        p_world.heightMapTh_plain = self.elevation['thresholds'][1][1]
        p_world.heightMapTh_hill = self.elevation['thresholds'][2][1]

        # Plates
        self._to_protobuf_matrix(self.plates, p_world.plates)

        # Ocean
        self._to_protobuf_matrix(self.ocean, p_world.ocean)
        self._to_protobuf_matrix(self.sea_depth, p_world.sea_depth)

        # Biome
        if hasattr(self, 'biome'):
            self._to_protobuf_matrix(self.biome, p_world.biome,
                                     biome_name_to_index)

        # Humidty
        if hasattr(self, 'humidity'):
            self._to_protobuf_matrix_with_quantiles(self.humidity,
                                                    p_world.humidity)

        if hasattr(self, 'irrigation'):
            self._to_protobuf_matrix(self.irrigation, p_world.irrigation)

        if hasattr(self, 'permeability'):
            self._to_protobuf_matrix(self.permeability['data'],
                                     p_world.permeabilityData)
            p_world.permeability_low = self.permeability['thresholds'][0][1]
            p_world.permeability_med = self.permeability['thresholds'][1][1]

        if hasattr(self, 'watermap'):
            self._to_protobuf_matrix(self.watermap['data'],
                                     p_world.watermapData)
            p_world.watermap_creek = self.watermap['thresholds']['creek']
            p_world.watermap_river = self.watermap['thresholds']['river']
            p_world.watermap_mainriver = self.watermap['thresholds'][
                'main river']

        if hasattr(self, 'lake_map'):
            self._to_protobuf_matrix(self.lake_map, p_world.lakemap)

        if hasattr(self, 'river_map'):
            self._to_protobuf_matrix(self.river_map, p_world.rivermap)

        if hasattr(self, 'precipitation'):
            self._to_protobuf_matrix(self.precipitation['data'],
                                     p_world.precipitationData)
            p_world.precipitation_low = self.precipitation['thresholds'][0][1]
            p_world.precipitation_med = self.precipitation['thresholds'][1][1]

        if hasattr(self, 'temperature'):
            self._to_protobuf_matrix(self.temperature['data'],
                                     p_world.temperatureData)
            p_world.temperature_polar = self.temperature['thresholds'][0][1]
            p_world.temperature_alpine = self.temperature['thresholds'][1][1]
            p_world.temperature_boreal = self.temperature['thresholds'][2][1]
            p_world.temperature_cool = self.temperature['thresholds'][3][1]
            p_world.temperature_warm = self.temperature['thresholds'][4][1]
            p_world.temperature_subtropical = \
                self.temperature['thresholds'][5][1]

        return p_world

    @classmethod
    def _from_protobuf_world(cls, p_world):
        w = World(p_world.name, p_world.width, p_world.height,
                  p_world.generationData.seed,
                  p_world.generationData.n_plates,
                  p_world.generationData.ocean_level,
                  Step.get_by_name(p_world.generationData.step))

        # Elevation
        e = World._from_protobuf_matrix(p_world.heightMapData)
        e_th = [('sea', p_world.heightMapTh_sea),
                ('plain', p_world.heightMapTh_plain),
                ('hill', p_world.heightMapTh_hill),
                ('mountain', None)]
        w.set_elevation(e, e_th)

        # Plates
        w.set_plates(World._from_protobuf_matrix(p_world.plates))

        # Ocean
        w.set_ocean(World._from_protobuf_matrix(p_world.ocean))
        w.sea_depth = World._from_protobuf_matrix(p_world.sea_depth)

        # Biome
        if len(p_world.biome.rows) > 0:
            w.set_biome(
                World._from_protobuf_matrix(
                    p_world.biome, biome_index_to_name))

        # Humidity
        # FIXME: use setters
        if len(p_world.humidity.rows) > 0:
            w.humidity = World._from_protobuf_matrix_with_quantiles(
                p_world.humidity)

        if len(p_world.irrigation.rows) > 0:
            w.irrigation = World._from_protobuf_matrix(p_world.irrigation)

        if len(p_world.permeabilityData.rows) > 0:
            p = World._from_protobuf_matrix(p_world.permeabilityData)
            p_th = [
                ('low', p_world.permeability_low),
                ('med', p_world.permeability_med),
                ('hig', None)
            ]
            w.set_permeability(p, p_th)

        if len(p_world.watermapData.rows) > 0:
            w.watermap = {}
            w.watermap['data'] = World._from_protobuf_matrix(
                p_world.watermapData)
            w.watermap['thresholds'] = {}
            w.watermap['thresholds']['creek'] = p_world.watermap_creek
            w.watermap['thresholds']['river'] = p_world.watermap_river
            w.watermap['thresholds']['main river'] = p_world.watermap_mainriver

        if len(p_world.precipitationData.rows) > 0:
            p = World._from_protobuf_matrix(p_world.precipitationData)
            p_th = [
                ('low', p_world.precipitation_low),
                ('med', p_world.precipitation_med),
                ('hig', None)
            ]
            w.set_precipitation(p, p_th)

        if len(p_world.temperatureData.rows) > 0:
            t = World._from_protobuf_matrix(p_world.temperatureData)
            t_th = [
                ('polar', p_world.temperature_polar),
                ('alpine', p_world.temperature_alpine),
                ('boreal', p_world.temperature_boreal),
                ('cool', p_world.temperature_cool),
                ('warm', p_world.temperature_warm),
                ('subtropical', p_world.temperature_subtropical),
                ('tropical', None)
            ]
            w.set_temperature(t, t_th)

        if len(p_world.lakemap.rows) > 0:
            m = World._from_protobuf_matrix(p_world.lakemap)
            w.set_lakemap(m)

        if len(p_world.rivermap.rows) > 0:
            m = World._from_protobuf_matrix(p_world.rivermap)
            w.set_rivermap(m)

        return w

    #
    # General
    #

    def contains(self, pos):
        x, y = pos
        return x >= 0 and y >= 0 and x < self.width and y < self.height

    #
    # Land/Ocean
    #

    def random_land(self):
        x, y = random_point(self.width, self.height)
        if self.ocean[y][x]:
            return self.random_land()
        else:
            return x, y

    def is_land(self, pos):
        x, y = pos
        return not self.ocean[y][x]

    def is_ocean(self, pos):
        x, y = pos
        return self.ocean[y][x]

    def sea_level(self):
        return self.elevation['thresholds'][0][1]

    #
    # Tiles around
    #

    def on_tiles_around_factor(self, factor, pos, radius=1, action=None):
        x, y = pos
        for dx in range(-radius, radius + 1):
            nx = x + dx
            if nx >= 0 and nx / factor < self.width:
                for dy in range(-radius, radius + 1):
                    ny = y + dy
                    if ny >= 0 and ny / factor < self.height and (
                                    dx != 0 or dy != 0):
                        action((nx, ny))

    def on_tiles_around(self, pos, radius=1, action=None):
        x, y = pos
        for dx in range(-radius, radius + 1):
            nx = x + dx
            if nx >= 0 and nx < self.width:
                for dy in range(-radius, radius + 1):
                    ny = y + dy
                    if ny >= 0 and ny < self.height and (dx != 0 or dy != 0):
                        action((nx, ny))

    def tiles_around(self, pos, radius=1, predicate=None):
        ps = []
        x, y = pos
        for dx in range(-radius, radius + 1):
            nx = x + dx
            if nx >= 0 and nx < self.width:
                for dy in range(-radius, radius + 1):
                    ny = y + dy
                    if ny >= 0 and ny < self.height and (dx != 0 or dy != 0):
                        if predicate is None or predicate((nx, ny)):
                            ps.append((nx, ny))
        return ps

    def tiles_around_factor(self, factor, pos, radius=1, predicate=None):
        ps = []
        x, y = pos
        for dx in range(-radius, radius + 1):
            nx = x + dx
            if nx >= 0 and nx < self.width * factor:
                for dy in range(-radius, radius + 1):
                    ny = y + dy
                    if ny >= 0 and ny < self.height * factor and (
                                    dx != 0 or dy != 0):
                        if predicate is None or predicate((nx, ny)):
                            ps.append((nx, ny))
        return ps

    def tiles_around_many(self, pos_list, radius=1, predicate=None):
        tiles = []
        for pos in pos_list:
            tiles += self.tiles_around(pos, radius, predicate)
        # remove duplicates
        # remove elements in pos
        return list(set(tiles) - set(pos_list))

    #
    # Elevation
    #

    def start_mountain_th(self):
        return self.elevation['thresholds'][2][1]

    def max_elevation(self):
        max_el = None
        for y in xrange(self.height):
            for x in xrange(self.width):
                el = self.elevation['data'][y][x]
                if max_el is None or el > max_el:
                    max_el = el
        return max_el

    def min_elevation(self):
        min_el = None
        for y in xrange(self.height):
            for x in xrange(self.width):
                el = self.elevation['data'][y][x]
                if min_el is None or el < min_el:
                    min_el = el
        return min_el

    def is_mountain(self, pos):
        if not self.is_land(pos):
            return False
        if len(self.elevation['thresholds']) == 4:
            mi = 2
        else:
            mi = 1
        mountain_level = self.elevation['thresholds'][mi][1]
        x, y = pos
        return self.elevation['data'][y][x] > mountain_level

    def is_low_mountain(self, pos):
        if not self.is_mountain(pos):
            return False
        if len(self.elevation['thresholds']) == 4:
            mi = 2
        else:
            mi = 1
        mountain_level = self.elevation['thresholds'][mi][1]
        x, y = pos
        return self.elevation['data'][y][x] < mountain_level + 2.0

    def level_of_mountain(self, pos):
        if not self.is_land(pos):
            return False
        if len(self.elevation['thresholds']) == 4:
            mi = 2
        else:
            mi = 1
        mountain_level = self.elevation['thresholds'][mi][1]
        x, y = pos
        if self.elevation['data'][y][x] <= mountain_level:
            return 0
        else:
            return self.elevation['data'][y][x] - mountain_level

    def is_high_mountain(self, pos):
        if not self.is_mountain(pos):
            return False
        if len(self.elevation['thresholds']) == 4:
            mi = 2
        else:
            mi = 1
        mountain_level = self.elevation['thresholds'][mi][1]
        x, y = pos
        return self.elevation['data'][y][x] > mountain_level + 4.0

    def is_hill(self, pos):
        if not self.is_land(pos):
            return False
        if len(self.elevation['thresholds']) == 4:
            hi = 1
        else:
            hi = 0
        hill_level = self.elevation['thresholds'][hi][1]
        mountain_level = self.elevation['thresholds'][hi + 1][1]
        x, y = pos
        return hill_level < self.elevation['data'][y][x] < mountain_level

    def elevation_at(self, pos):
        x, y = pos
        return self.elevation['data'][y][x]

    #
    # Temperature
    #

    def is_temperature_polar(self, pos):
        th_max = self.temperature['thresholds'][0][1]
        x, y = pos
        t = self.temperature['data'][y][x]
        return t < th_max

    def is_temperature_alpine(self, pos):
        th_min = self.temperature['thresholds'][0][1]
        th_max = self.temperature['thresholds'][1][1]
        x, y = pos
        t = self.temperature['data'][y][x]
        return th_max > t >= th_min

    def is_temperature_boreal(self, pos):
        th_min = self.temperature['thresholds'][1][1]
        th_max = self.temperature['thresholds'][2][1]
        x, y = pos
        t = self.temperature['data'][y][x]
        return th_max > t >= th_min

    def is_temperature_cool(self, pos):
        th_min = self.temperature['thresholds'][2][1]
        th_max = self.temperature['thresholds'][3][1]
        x, y = pos
        t = self.temperature['data'][y][x]
        return th_max > t >= th_min

    def is_temperature_warm(self, pos):
        th_min = self.temperature['thresholds'][3][1]
        th_max = self.temperature['thresholds'][4][1]
        x, y = pos
        t = self.temperature['data'][y][x]
        return th_max > t >= th_min

    def is_temperature_subtropical(self, pos):
        th_min = self.temperature['thresholds'][4][1]
        th_max = self.temperature['thresholds'][5][1]
        x, y = pos
        t = self.temperature['data'][y][x]
        return th_max > t >= th_min

    def is_temperature_tropical(self, pos):
        th_min = self.temperature['thresholds'][5][1]
        x, y = pos
        t = self.temperature['data'][y][x]
        return t >= th_min

    #
    # Humidity
    #

    def is_humidity_above_quantile(self, pos, q):
        th = self.humidity['quantiles'][str(q)]
        x, y = pos
        v = self.humidity['data'][y][x]
        return v >= th

    def is_humidity_superarid(self, pos):
        th_max = self.humidity['quantiles']['87']
        x, y = pos
        t = self.humidity['data'][y][x]
        return t < th_max

    def is_humidity_perarid(self, pos):
        th_min = self.humidity['quantiles']['87']
        th_max = self.humidity['quantiles']['75']
        x, y = pos
        t = self.humidity['data'][y][x]
        return th_max > t >= th_min

    def is_humidity_arid(self, pos):
        th_min = self.humidity['quantiles']['75']
        th_max = self.humidity['quantiles']['62']
        x, y = pos
        t = self.humidity['data'][y][x]
        return th_max > t >= th_min

    def is_humidity_semiarid(self, pos):
        th_min = self.humidity['quantiles']['62']
        th_max = self.humidity['quantiles']['50']
        x, y = pos
        t = self.humidity['data'][y][x]
        return th_max > t >= th_min

    def is_humidity_subhumid(self, pos):
        th_min = self.humidity['quantiles']['50']
        th_max = self.humidity['quantiles']['37']
        x, y = pos
        t = self.humidity['data'][y][x]
        return th_max > t >= th_min

    def is_humidity_humid(self, pos):
        th_min = self.humidity['quantiles']['37']
        th_max = self.humidity['quantiles']['25']
        x, y = pos
        t = self.humidity['data'][y][x]
        return th_max > t >= th_min

    def is_humidity_perhumid(self, pos):
        th_min = self.humidity['quantiles']['25']
        th_max = self.humidity['quantiles']['12']
        x, y = pos
        t = self.humidity['data'][y][x]
        return th_max > t >= th_min

    def is_humidity_superhumid(self, pos):
        th_min = self.humidity['quantiles']['12']
        x, y = pos
        t = self.humidity['data'][y][x]
        return t >= th_min

    #
    # Streams
    #

    def contains_stream(self, pos):
        return self.contains_creek(pos) or self.contains_river(
            pos) or self.contains_main_river(pos)

    def contains_creek(self, pos):
        x, y = pos
        v = self.watermap['data'][y][x]
        return self.watermap['thresholds']['creek'] <= v < \
            self.watermap['thresholds']['river']

    def contains_river(self, pos):
        x, y = pos
        v = self.watermap['data'][y][x]
        return self.watermap['thresholds']['river'] <= v < \
            self.watermap['thresholds']['main river']

    def contains_main_river(self, pos):
        x, y = pos
        v = self.watermap['data'][y][x]
        return v >= self.watermap['thresholds']['main river']

    def watermap_at(self, pos):
        x, y = pos
        return self.watermap['data'][y][x]

    #
    # Biome
    #

    def biome_at(self, pos):
        x, y = pos
        b = Biome.by_name(self.biome[y][x])
        if b is None:
            raise Exception('Not found')
        return b

    def is_boreal_forest(self, pos):
        if isinstance(self.biome_at(pos), BorealMoistForest):
            return True
        elif isinstance(self.biome_at(pos), BorealWetForest):
            return True
        elif isinstance(self.biome_at(pos), BorealRainForest):
            return True
        else:
            return False

    def is_temperate_forest(self, pos):
        if isinstance(self.biome_at(pos), CoolTemperateMoistForest):
            return True
        elif isinstance(self.biome_at(pos), CoolTemperateWetForest):
            return True
        elif isinstance(self.biome_at(pos), CoolTemperateRainForest):
            return True
        else:
            return False

    def is_warm_temperate_forest(self, pos):
        if isinstance(self.biome_at(pos), WarmTemperateMoistForest):
            return True
        elif isinstance(self.biome_at(pos), WarmTemperateWetForest):
            return True
        elif isinstance(self.biome_at(pos), WarmTemperateRainForest):
            return True
        else:
            return False

    def is_tropical_dry_forest(self, pos):
        if isinstance(self.biome_at(pos), SubtropicalDryForest):
            return True
        elif isinstance(self.biome_at(pos), TropicalDryForest):
            return True
        else:
            return False

    def is_tundra(self, pos):
        if isinstance(self.biome_at(pos), SubpolarMoistTundra):
            return True
        elif isinstance(self.biome_at(pos), SubpolarWetTundra):
            return True
        elif isinstance(self.biome_at(pos), SubpolarRainTundra):
            return True
        else:
            return False

    def is_iceland(self, pos):
        if isinstance(self.biome_at(pos), Ice):
            return True
        elif isinstance(self.biome_at(pos), PolarDesert):
            return True
        else:
            return False

    def is_jungle(self, pos):
        if isinstance(self.biome_at(pos), SubtropicalMoistForest):
            return True
        elif isinstance(self.biome_at(pos), SubtropicalWetForest):
            return True
        elif isinstance(self.biome_at(pos), SubtropicalRainForest):
            return True
        elif isinstance(self.biome_at(pos), TropicalMoistForest):
            return True
        elif isinstance(self.biome_at(pos), TropicalWetForest):
            return True
        elif isinstance(self.biome_at(pos), TropicalRainForest):
            return True
        else:
            return False

    def is_savanna(self, pos):
        if isinstance(self.biome_at(pos), SubtropicalThornWoodland):
            return True
        elif isinstance(self.biome_at(pos), TropicalThornWoodland):
            return True
        elif isinstance(self.biome_at(pos), TropicalVeryDryForest):
            return True
        else:
            return False

    def is_hot_desert(self, pos):
        if isinstance(self.biome_at(pos), WarmTemperateDesert):
            return True
        elif isinstance(self.biome_at(pos), WarmTemperateDesertScrub):
            return True
        elif isinstance(self.biome_at(pos), SubtropicalDesert):
            return True
        elif isinstance(self.biome_at(pos), SubtropicalDesertScrub):
            return True
        elif isinstance(self.biome_at(pos), TropicalDesert):
            return True
        elif isinstance(self.biome_at(pos), TropicalDesertScrub):
            return True
        else:
            return False

    def is_cold_parklands(self, pos):
        if isinstance(self.biome_at(pos), SubpolarDryTundra):
            return True
        elif isinstance(self.biome_at(pos), BorealDesert):
            return True
        elif isinstance(self.biome_at(pos), BorealDryScrub):
            return True
        else:
            return False

    def is_steppe(self, pos):
        if isinstance(self.biome_at(pos), CoolTemperateSteppe):
            return True
        else:
            return False

    def is_cool_desert(self, pos):
        if isinstance(self.biome_at(pos), CoolTemperateDesert):
            return True
        elif isinstance(self.biome_at(pos), CoolTemperateDesertScrub):
            return True
        else:
            return False

    def is_chaparral(self, pos):
        """ Chaparral is a shrubland or heathland plant community.

        For details see http://en.wikipedia.org/wiki/Chaparral.
        """
        if isinstance(self.biome_at(pos), WarmTemperateThornScrub):
            return True
        elif isinstance(self.biome_at(pos), WarmTemperateDryForest):
            return True
        else:
            return False

    #
    # Plates
    #

    def n_actual_plates(self):
        res = -1
        for row in self.plates:
            for cell in row:
                res = max([cell, res])
        return res + 1

    #
    # Setters
    #

    def set_elevation(self, data, thresholds):
        if (len(data) != self.height) or (len(data[0]) != self.width):
            raise Exception(
                "Setting elevation map with wrong dimension. " +
                "Expected %d x %d, found %d x %d" % (
                    self.width, self.height, (len[data[0]], len(data))))
        self.elevation = {'data': data, 'thresholds': thresholds}

    def set_plates(self, data):
        if (len(data) != self.height) or (len(data[0]) != self.width):
            raise Exception(
                "Setting plates map with wrong dimension. " +
                "Expected %d x %d, found %d x %d" % (
                    self.width, self.height, (len[data[0]], len(data))))
        self.plates = data

    def set_biome(self, biome):
        if len(biome) != self.height:
            raise Exception(
                "Setting data with wrong height: biome has height %i while " +
                "the height is currently %i" % (
                    len(biome), self.height))
        if len(biome[0]) != self.width:
            raise Exception("Setting data with wrong width")

        self.biome = biome

    def set_ocean(self, ocean):
        if (len(ocean) != self.height) or (len(ocean[0]) != self.width):
            raise Exception(
                "Setting ocean map with wrong dimension. Expected %d x %d, " +
                "found %d x %d" % (self.width, self.height,
                                   len(ocean[0]), len(ocean)))

        self.ocean = ocean

    def set_precipitation(self, data, thresholds):
        """"Precipitation is a value in [-1,1]"""

        if len(data) != self.height:
            raise Exception("Setting data with wrong height")
        if len(data[0]) != self.width:
            raise Exception("Setting data with wrong width")

        self.precipitation = {'data': data, 'thresholds': thresholds}

    def set_temperature(self, data, thresholds):
        if len(data) != self.height:
            raise Exception("Setting data with wrong height")
        if len(data[0]) != self.width:
            raise Exception("Setting data with wrong width")

        self.temperature = {'data': data, 'thresholds': thresholds}

    def set_permeability(self, data, thresholds):
        if len(data) != self.height:
            raise Exception("Setting data with wrong height")
        if len(data[0]) != self.width:
            raise Exception("Setting data with wrong width")

        self.permeability = {'data': data, 'thresholds': thresholds}

    def has_precipitations(self):
        return hasattr(self, 'precipitation')

    def has_watermap(self):
        return hasattr(self, 'watermap')

    def has_irrigation(self):
        return hasattr(self, 'irrigation')

    def has_humidity(self):
        return hasattr(self, 'humidity')

    def has_temperature(self):
        return hasattr(self, 'temperature')

    def has_permeability(self):
        return hasattr(self, 'permeability')

    def has_biome(self):
        return hasattr(self, 'biome')

    def set_rivermap(self, river_map):
        self.river_map = river_map

    def set_lakemap(self, lake_map):
        self.lake_map = lake_map

    def __rescale_matrix__(self, matrix, new_width, new_height):
        base_value = None
        if type(matrix[0][0])==int:
            return rescale_int_matrix(matrix, new_width, new_height)
        elif type(matrix[0][0])==float:
            return rescale_float_matrix(matrix, new_width, new_height)
        elif type(matrix[0][0])==bool:
            base_value = False
        else:
            raise Exception("Unknown matrix value %s" % type(matrix[0][0]))

        rescaled_matrix = [[base_value for x in range(new_width)] for y in range(new_height)]
        #return rescaled_matrix
        return matrix

    def rescale(self, new_width, new_height):
        self.elevation['data'] = self.__rescale_matrix__(self.elevation['data'], new_width, new_height)
        self.plates = self.__rescale_matrix__(self.plates, new_width, new_height)
        self.ocean = self.__rescale_matrix__(self.ocean, new_width, new_height)
        self.sea_depth = self.__rescale_matrix__(self.sea_depth, new_width, new_height)

        if hasattr(self, 'biome'):
            self.biome = self.__rescale_matrix__(self.biome, new_width, new_height)
        if hasattr(self, 'humidity'):
            self.humidity['data'] = self.__rescale_matrix__(self.humidity['data'], new_width, new_height)
        if hasattr(self, 'irrigation'):
            self.irrigation = self.__rescale_matrix__(self.irrigation, new_width, new_height)
        if hasattr(self, 'permeability'):
            self.permeability = self.__rescale_matrix__(self.permeability, new_width, new_height)
        if hasattr(self, 'watermap'):
            self.watermap['data'] = self.__rescale_matrix__(self.watermap['data'], new_width, new_height)
        if hasattr(self, 'lake_map'):
            self.lake_map = self.__rescale_matrix__(self.lake_map, new_width, new_height)
        if hasattr(self, 'river_map'):
            self.river_map = self.__rescale_matrix__(self.river_map, new_width, new_height)
        if hasattr(self, 'precipitation'):
            self.precipitation['data'] = self.__rescale_matrix__(self.precipitation['data'], new_width, new_height)
        if hasattr(self, 'temperature'):
            self.temperature['data'] = self.__rescale_matrix__(self.temperature['data'], new_width, new_height)
        self.width = new_width
        self.height = new_height
