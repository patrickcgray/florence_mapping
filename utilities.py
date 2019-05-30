import rasterio
from rasterio.plot import adjust_band
import matplotlib.pyplot as plt
from rasterio.plot import reshape_as_raster, reshape_as_image
from rasterio.plot import show
from rasterio.windows import Window
import rasterio.features
import rasterio.warp
import rasterio.mask
from shapely.geometry import Polygon
from pyproj import Proj, transform
import numpy as np



def read_windows(rasters, c, r, buffer, tile_size):
    tiles = []
    #only works when rasters are in same projection
    for raster in rasters:
        tile = raster.read(list(np.arange(1, raster.count+1)), window=Window(c-buffer, r-buffer, tile_size, tile_size))
        tiles.append(tile)
    return (*tiles,)

def get_class_count():
    return len(class_names)

def merge_classes(y):
    y[y == 22] = 23
    y[y == 24] = 23
    return y
   
def make_label_mask(landsat, label):
    image_dataset = landsat
    label_proj = Proj(label.crs)
    raster_points = image_dataset.transform * (0, 0), image_dataset.transform * (image_dataset.width, 0), image_dataset.transform * (image_dataset.width, image_dataset.height), image_dataset.transform * (0, image_dataset.height)
    l8_proj = Proj(image_dataset.crs)
    new_raster_points = []
    # convert the raster bounds from landsat into label crs
    for x,y in raster_points:
        x,y = transform(l8_proj,label_proj,x,y)
        # convert from crs into row, col in label image coords
        row, col = label.index(x, y)
        # don't forget row, col is actually y, x so need to swap it when we append
        new_raster_points.append((col, row))
        # turn this into a polygon
    raster_poly = Polygon(new_raster_points)
        # Window.from_slices((row_start, row_stop), (col_start, col_stop))
    masked_label_image = label.read(window=Window.from_slices((int(raster_poly.bounds[1]), int(raster_poly.bounds[3])), (int(raster_poly.bounds[0]), int(raster_poly.bounds[2]))))
    return masked_label_image, raster_poly

def load_data():
    label_dataset = rasterio.open('/deep_data/NLCD/NLCD_2016_Land_Cover_L48_20190424.img')

    l8_image_paths = [
    '/deep_data/processed_landsat/LC08_CU_027012_20170907_20181121_C01_V01_SR_combined.tif',
    '/deep_data/processed_landsat/LC08_CU_028011_20170907_20181130_C01_V01_SR_combined.tif',  
    '/deep_data/processed_landsat/LC08_CU_028012_20171002_20171019_C01_V01_SR_combined.tif',
    '/deep_data/processed_landsat/LC08_CU_028012_20171103_20190429_C01_V01_SR_combined.tif',
    '/deep_data/processed_landsat/LC08_CU_029011_20171018_20190429_C01_V01_SR_combined.tif'
    ]

    s1_image_paths = [
    '/deep_data/sentinel_sar/LC08_CU_027012_20170907_20181121_C01_V01_SR_combined/aligned-LC08_CU_027012_20170907_20181121_C01_V01_SR_combined_SAR.tif',
    '/deep_data/sentinel_sar/LC08_CU_028011_20170907_20181130_C01_V01_SR_combined/aligned-LC08_CU_028011_20170907_20181130_C01_V01_SR_combined_SAR.tif',
    '/deep_data/sentinel_sar/LC08_CU_028012_20171002_20171019_C01_V01_SR_combined/aligned-LC08_CU_028012_20171002_20171019_C01_V01_SR_combined_SAR.tif',
    '/deep_data/sentinel_sar/LC08_CU_028012_20171103_20190429_C01_V01_SR_combined/aligned-LC08_CU_028012_20171103_20190429_C01_V01_SR_combined_SAR.tif',
    '/deep_data/sentinel_sar/LC08_CU_029011_20171018_20190429_C01_V01_SR_combined/aligned-LC08_CU_029011_20171018_20190429_C01_V01_SR_combined_SAR.tif',
   ]

    dem_image_paths = [
    '/deep_data/sentinel_sar/LC08_CU_027012_20170907_20181121_C01_V01_SR_combined_dem/aligned-wms_DEM_EPSG4326_-79.69001_33.95762_-77.7672_35.51886__4500X4631_ShowLogo_False_tiff_depth=32f.tiff',
    '/deep_data/sentinel_sar/LC08_CU_028011_20170907_20181130_C01_V01_SR_combined_dem/aligned-wms_DEM_EPSG4326_-77.7672_35.00779_-75.79042_36.58923__4500X4262_ShowLogo_False_tiff_depth=32f.tiff',
    '/deep_data/sentinel_sar/LC08_CU_028012_20171002_20171019_C01_V01_SR_combined_dem/aligned-wms_DEM_EPSG4326_-79.69001_33.95762_-77.7672_35.51886__4500X4631_ShowLogo_False_tiff_depth=32f.tiff',
    '/deep_data/sentinel_sar/LC08_CU_028012_20171103_20190429_C01_V01_SR_combined_dem/aligned-wms_DEM_EPSG4326_-78.07896_33.69485_-76.14021_35.27466__4500X4248_ShowLogo_False_tiff_depth=32f.tiff',
    '/deep_data/sentinel_sar/LC08_CU_029011_20171018_20190429_C01_V01_SR_combined_dem/aligned-wms_DEM_EPSG4326_-76.14021_34.71847_-74.14865_36.318__4500X4408_ShowLogo_False_tiff_depth=32f.tiff',
    ]

    landsat_datasets = []
    for fp in l8_image_paths:
        landsat_datasets.append(rasterio.open(fp))
    sentinel_datasets = []
    for fp in s1_image_paths:
        sentinel_datasets.append(rasterio.open(fp))
    dem_datasets = []
    for fp in dem_image_paths:
        dem_datasets.append(rasterio.open(fp))
    return (landsat_datasets, sentinel_datasets, dem_datasets, label_dataset)      
        


class_names = dict((
(11, "Water"),
(12, "Snow/Ice"),
(21, "Open Space Developed"),
(22, "Low Intensity Developed"),
(23, "Medium Intensity Developed"),
(24, "High Intensity Developed"),
(31, "Barren Land"),
(41, "Deciduous Forest"),
(42, "Evergreen Forest"),
(43, "Mixed Forest"),
#(51, "Dwarf Scrub/Shrub - ALASKA"),
(52, "Scrub/Shrub"),
(71, "Grassland / Herbaceous"),
#(72, "Sedge / Herbaceous - ALASKA"),
#(73, "Lichen / Herbaceous - ALASKA"),
#(74, "Moss - ALASKA"),
(81, "Pasture/Hay"),
(82, "Cultivated Land"),
(90, "Woody Wetland"),
(95, "Emergent Herbaceous Wetlands"),
))


colors = dict((
    (11, (0,0,255)), #water ~ blue
(12, (0,0,255)), #snow ~ white
(21, (255,0,0)), #open space developed ~ red
(22, (50,0,0)), # low intensity developed ~ darker red
(23, (50,0,0)), # medium intensity developed ~ darker darker red
(24, (50,0,0)), # high intensity developed ~ darker darker darker red
(31, (153,76,0)), # barren land ~ dark orange
(41, (0,204,0)), # deciduous forest ~ green
(42, (0,153,0)), # evergreen forest ~ darker green
(43, (0,102,0)), # mixed forest ~ darker darker green
(52, (153,0,76)), #schrub ~ dark pink
(71, (255,153,71)), # grass land ~  orange
(81, (204,204,0)),#pasture ~ yellowish
(82, (153,153,0)),#cultivated land ~ darker yellow
(90, (0,255,255)), #woody wetland ~ aqua
(95, (0,102,102)), #emergent herbaceous wetlands ~ darker aqua
))

class_to_index = dict((
(11, 0),
(12, 1),
(21, 2),
(22, 3),
(23, 4),
(24, 5),
(31, 6),
(41, 7),
(42, 8),
(43, 9),
(52, 10),
(71, 11),
(81, 12),
(82, 13),
(90, 14),
(95, 15),
))


indexed_dictionary = dict((
(0, "Water"),
(1, "Snow/Ice"),
(2, "Open Space Developed"),
(3, "Low Intensity Developed"),
(4, "Medium Intensity Developed"),
(5, "High Intensity Developed"),
(6, "Barren Land"),
(7, "Deciduous Forest"),
(8, "Evergreen Forest"),
(9, "Mixed Forest"),
#(51, "Dwarf Scrub/Shrub - ALASKA"),
(10, "Scrub/Shrub"),
(11, "Grassland / Herbaceous"),
#(72, "Sedge / Herbaceous - ALASKA"),
#(73, "Lichen / Herbaceous - ALASKA"),
#(74, "Moss - ALASKA"),
(12, "Pasture/Hay"),
(13, "Cultivated Land"),
(14, "Woody Wetland"),
(15, "Emergent Herbaceous Wetlands"),
))