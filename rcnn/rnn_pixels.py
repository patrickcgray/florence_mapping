import rasterio
import numpy as np
import random
import math
import itertools
from rasterio.windows import Window
from pyproj import Proj, transform
from tqdm import tqdm
from shapely.geometry import Polygon, Point
import geopandas as gpd
import os
import sys
module_path = os.path.abspath(os.path.join('..'))
if module_path not in sys.path:
    sys.path.append(module_path)
import utilities as util
import importlib
import rnn_tiles

def make_pixels(tile_size, tile_list, shuffle=True):
    # return every potentially viable center tile location from all landsat images shuffled
    points = []
    l8_points = []
    buffer = math.floor(tile_size/2)
    x = np.arange(0+buffer, 5000-buffer, tile_size)
    y = np.arange(0+buffer, 5000-buffer, tile_size)
    for row in y:
        for col in x:
            point = (row, col)
            points.append(point)
    #tile_list = ['028012', '029011','028011']
    for tile in tile_list:
        for point in points:
            l8_points.append((point, tile))
    if shuffle:
        random.shuffle(l8_points)
    return l8_points


#def gen_pixel_locations(l8_data, pixel_count, tile_size):
#    pixels = []
#    buffer = math.floor(tile_size/2)
#    count_per_dataset = math.ceil(pixel_count / len(l8_data))
#    for index, l8_d in l8_data.items():
        #randomly pick `count` num of pixels from each dataset
#        img_height, img_width = l8_d[0].shape
#        rows = range(0+buffer, img_height-buffer)
#        columns = range(0+buffer, img_width-buffer)
#        points = random.sample(set(itertools.product(rows, columns)), math.ceil(10*count_per_dataset))
#        dataset_index_list = [index] * math.ceil(10*count_per_dataset)
#        dataset_pixels = list(zip(points, dataset_index_list))
      #  dataset_pixels = delete_black_tiles(l8_data, tile_size, dataset_pixels, max_size = count_per_dataset)
 #       pixels += dataset_pixels
 #   return (pixels)

def train_val_test_split(pixels, train_val_ratio, val_test_ratio):
    random.shuffle(pixels)
    train_px = pixels[:int(len(pixels)*train_val_ratio)]
    val_pixels = pixels[int(len(pixels)*train_val_ratio):]
    val_px = val_pixels[:int(len(val_pixels)*val_test_ratio)]
    test_px = val_pixels[int(len(val_px)*val_test_ratio):]
    print("train:{} val:{} test:{}".format(len(train_px), len(val_px), len(test_px)))
    return (train_px, val_px, test_px)
    
def delete_bad_tiles(l8_data, lc_label, canopy_label, pixels, tile_size, buffer_pix=None):
    buffer = math.floor(tile_size / 2)
    cloud_list = [-999999] # nothing # high confidence cloud [224] # full list [72, 80, 96, 130, 132, 136, 160, 224]
    new_pixels = []
    l8_proj = Proj(l8_data['028012'][0].crs)
    lc_proj = Proj(lc_label.crs)
    canopy_proj = Proj(canopy_label.crs)
    counter = 0
    center_index = math.floor(tile_size / 2)
    for pixel in pixels:
        r, c = pixel[0]
        dataset_index = pixel[1]
        tiles_to_read = l8_data[dataset_index]
        tiles_read = util.read_windows(tiles_to_read, c ,r, buffer, tile_size)
        (x, y) = l8_data[dataset_index][0].xy(r, c) 
        # convert the point we're sampling from to the same projection as the label dataset if necessary
        #if l8_proj != lc_proj:
            #lc_x,lc_y = transform(l8_proj,lc_proj,x,y)
        lc_x,lc_y = x,y
        # these are broken and not working for some reason because pyproj doesn't understand the canopy projection
        #if l8_proj != canopy_proj:
        #    canopy_x, canopy_y = transform(l8_proj,canopy_proj,x,y)
        # but luckily there only a couple cm different so it shouldn't matter
        canopy_x = x
        canopy_y = y
        # reference gps in label_image
        lc_row, lc_col = lc_label.index(lc_x,lc_y)
 
        lc_data = lc_label.read(1, window=Window(lc_col-buffer, lc_row-buffer, tile_size, tile_size))
        canopy_row, canopy_col = canopy_label.index(canopy_x,canopy_y)
        canopy_data = canopy_label.read(1, window=Window(canopy_col-buffer, canopy_row-buffer, tile_size, tile_size))
        flag = True
        # this used to eliminate pixels with only a single value to balance the FCN but now we don't want that
        #if len(np.unique(lc_data)) == 1 and 11 in lc_data and tile_size != 1:
        #    flag = False
        
        if 0 in lc_data or np.nan in lc_data or np.nan in canopy_data or 255 in canopy_data or canopy_data.shape != (tile_size, tile_size):
            flag = False
        #counter += 1
        
        if flag:
            # TODO this can very likely be optimized and doesn't need to be a for loop
            for tile in tiles_read:
                if np.isnan(tile).any() == True or -9999 in tile or tile.size == 0 or np.amax(tile) == 0 or np.isin(tile[7,:,:], cloud_list).any() or tile.shape != (l8_data[dataset_index][0].count, tile_size, tile_size):
                    flag = False
                    break
                
        if buffer_pix and flag:
            # check all surrounding pixels with a radius of buffer_pix and if any are a different value then 
            # flag it and don't include it in the output
            lc_data_merged = np.vectorize(util.class_to_index.get)(lc_data)
            if len(np.unique(lc_data_merged[center_index-buffer_pix:center_index+buffer_pix+1, center_index-buffer_pix:center_index+buffer_pix+1])) != 1:
                flag = False
        
        if flag:
            new_pixels.append(pixel)
            
        if counter % 1000 == 0:
            #print(counter)
            pass
    return new_pixels    

def make_clean_pix(tile_list, tile_size, landsat_datasets,lc_labels, canopy_labels, pix_count, buffer_pix=1):
    px = make_pixels(tile_size, tile_list)
    px_to_use = px[:pix_count]
    pixels = delete_bad_tiles(landsat_datasets,lc_labels, canopy_labels, px_to_use, tile_size, buffer_pix=buffer_pix)
    return(pixels)

def balanced_pix_locations(landsat_datasets, lc_labels, canopy_labels, tile_size, tile_list, 
            clean_pixels_count, class_count, count_per_class, class_dict, buffer_pix=1, print_class_counts=True):
    # gets shuffled and balanced pixels locations ready for ingestion by model
    
    print("Beginning balanced pixel creation.")

    pixels = make_clean_pix(tile_list, tile_size, landsat_datasets,lc_labels, canopy_labels, 
                                       clean_pixels_count, buffer_pix=1)
    
    print("Clean pix generated, starting generator.")
   
    w_tile_gen = rnn_tiles.rnn_tile_gen(landsat_datasets, lc_labels, canopy_labels, tile_size, class_count)
    w_generator = w_tile_gen.tile_generator(pixels, batch_size=1, flatten=True, canopy=True)
    
    print("Iterating through data and clipping for balance.")

    buckets = {}

    for key in class_dict:
        buckets[key] = []


    count = 0
    while count < len(pixels):
            image_b, label_b = next(w_generator)
            label_b = np.argmax(label_b['landcover'])
            buckets[label_b].append(pixels[count]) # appends pixels to dictionary
            count+=1

    count_dict = {}
    for z, j in buckets.items():
        count_dict[class_dict[z]] = len(j)
        
    use_px = []
    for key in class_dict:
        use_px+=buckets[key][:count_per_class]

    random.shuffle(use_px)
    train_px, val_px, test_px = train_val_test_split(use_px, 0.8, 0.8)
    
    print("\nProcessing Complete.")
    
    return(train_px, val_px, test_px, count_dict)

def tvt_pix_locations(landsat_datasets, lc_labels, canopy_labels, tile_size, tile_list, 
            pixels, test_per_class, val_per_class, train_per_class, class_dict):
    # gets shuffled and balanced pixels locations ready for ingestion by model
    
    print("Beginning TVT pixel creation.")
    
    class_count = len(class_dict)
    tile_buffer = int(tile_size / 2)
   
    w_tile_gen = rnn_tiles.rnn_tile_gen(landsat_datasets, lc_labels, canopy_labels, 1, class_count)
    w_generator = w_tile_gen.tile_generator(pixels, batch_size=1, flatten=True, canopy=True)
    
    print("Iterating through data and clipping for balance.")
    
    tile_dict = {}
    for idx, item in enumerate(tile_list):
        tile_dict[item] = idx

    test_buckets = {}
    val_buckets = {}
    train_buckets = {}
    
    test_count = 0
    val_count = 0
    train_count = 0
    count = 0

    for key in class_dict:
        test_buckets[key] = []
        val_buckets[key] = []
        train_buckets[key] = []
        
    # this is for quickly checking if pixels overlap
    # structure should be row, col, tile
    pixel_matrix = np.zeros((5000,5000, len(tile_list)))
    
    test_total = test_per_class * class_count    
    val_total = val_per_class * class_count    
    train_total = train_per_class * class_count    
        
    # buffering is already done, all pix are homogenous
    
    exclusion_shp = gpd.read_file('exclusion.shp')
    exclusion_shp = exclusion_shp.to_crs('PROJCS["Albers",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378140,298.2569999999957,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]],PROJECTION["Albers_Conic_Equal_Area"],PARAMETER["standard_parallel_1",29.5],PARAMETER["standard_parallel_2",45.5],PARAMETER["latitude_of_center",23],PARAMETER["longitude_of_center",-96],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]]]')
    exclusion_poly = exclusion_shp.geometry[0]
    
    # test data
    # if there are still more test pixels needed overall
    while test_count < test_total:
        if count >= len(pixels):
            break
        image_b, label_b = next(w_generator)
        label_b = np.argmax(label_b['landcover'])
        # if there are more test pixels needed in this specific class
        if len(test_buckets[label_b]) < test_per_class:
            pixel_coords = pixels[count][0]
            landsat_tile = pixels[count][1]
            tile_index = tile_dict[landsat_tile]
            # coords are of format (row, col)
            x_loc = pixel_coords[1]
            y_loc = pixel_coords[0]
            # create exclusion buffers where the other pixels cannot be
            xmin = x_loc-1
            xmax = x_loc+1+1
            ymin = y_loc-1
            ymax = y_loc+1+1
            # if that pixel doesn't fall within 1 px of existing test pixels then continue
            if not(np.isin(pixel_matrix[ymin:ymax, xmin:xmax, tile_index], 1).any()):
                # exclude the confusing mine area
                #if label_b == 4:
                p1 = Point(landsat_datasets[landsat_tile][0].xy(y_loc,x_loc))
                if p1.within(exclusion_poly):
                    pass
                else:
                    test_buckets[label_b].append(pixels[count]) # appends pixels to dictionary
                    pixel_matrix[pixel_coords + (tile_index,)] = 1
                    test_count+=1
        count += 1       
    
    w_generator.close()

    # validation data
    count = 0
    w_generator = w_tile_gen.tile_generator(pixels, batch_size=1, flatten=True, canopy=True)
    while val_count < val_total:
        if count >= len(pixels):
            break
        image_b, label_b = next(w_generator)
        label_b = np.argmax(label_b['landcover'])
        # if there are more val pixels needed in this specific class
        if len(val_buckets[label_b]) < val_per_class:
            pixel_coords = pixels[count][0]
            landsat_tile = pixels[count][1]
            tile_index = tile_dict[landsat_tile]
            x_loc = pixel_coords[1]
            y_loc = pixel_coords[0]
            # create exclusion buffers so there is no overlap with test data
            xmin = x_loc-tile_buffer
            xmax = x_loc+tile_buffer+1
            ymin = y_loc-tile_buffer
            ymax = y_loc+tile_buffer+1
            if not(np.isin(pixel_matrix[ymin:ymax, xmin:xmax, tile_index], 1).any()):
                xmin = x_loc-1
                xmax = x_loc+1+1
                ymin = y_loc-1
                ymax = y_loc+1+1
                # if that pixel doesn't fall within 1 px of existing val pixels then continue
                if not(np.isin(pixel_matrix[ymin:ymax, xmin:xmax, tile_index], 2).any()):
                    # exclude the confusing mine area
                    if label_b == 4:
                        p1 = Point(landsat_datasets[landsat_tile][0].xy(y_loc,x_loc))
                        if p1.within(exclusion_poly):
                            pass
                        else:
                            val_buckets[label_b].append(pixels[count]) # appends pixels to dictionary
                            pixel_matrix[pixel_coords + (tile_index,)] = 2
                            val_count+=1
                    else:
                        val_buckets[label_b].append(pixels[count]) # appends pixels to dictionary
                        pixel_matrix[pixel_coords + (tile_index,)] = 2
                        val_count+=1
        count += 1 
     
    w_generator.close()
        
    # train data
    count = 0
    w_generator = w_tile_gen.tile_generator(pixels, batch_size=1, flatten=True, canopy=True)
    
    while train_count < train_total:
        if count >= len(pixels):
            break
        image_b, label_b = next(w_generator)
        label_b = np.argmax(label_b['landcover'])
        # if there are more train pixels needed in this specific class
        if len(train_buckets[label_b]) < train_per_class:
            pixel_coords = pixels[count][0]
            landsat_tile = pixels[count][1]
            tile_index = tile_dict[landsat_tile]
            x_loc = pixel_coords[1]
            y_loc = pixel_coords[0]
            # create exclusion buffers so there is no overlap with test data
            xmin = x_loc-tile_buffer
            xmax = x_loc+tile_buffer+1
            ymin = y_loc-tile_buffer
            ymax = y_loc+tile_buffer+1
            if not(np.isin(pixel_matrix[ymin:ymax, xmin:xmax, tile_index], 1).any()):
                if not(np.isin(pixel_matrix[ymin:ymax, xmin:xmax, tile_index], 2).any()):
                    if not(np.isin(pixel_matrix[x_loc, y_loc, tile_index], 3).any()):
                        # exclude the confusing mine area
                        if label_b == 4:
                            p1 = Point(landsat_datasets[landsat_tile][0].xy(y_loc,x_loc))
                            if p1.within(exclusion_poly):
                                pass
                            else:
                                train_buckets[label_b].append(pixels[count]) # appends pixels to dictionary
                                pixel_matrix[pixel_coords + (tile_index,)] = 3
                                train_count+=1
                        else:
                            train_buckets[label_b].append(pixels[count])
                            pixel_matrix[pixel_coords + (tile_index,)] = 3
                            train_count+=1
        count += 1 
        
    w_generator.close()

    
    train_px = []
    val_px = []
    test_px = []
    
    for key in class_dict:
        test_px+=test_buckets[key]
        val_px+=val_buckets[key]
        train_px+=train_buckets[key]

#     random.shuffle(test_px)
#     random.shuffle(val_px)
#     random.shuffle(train_px)
    print("\nProcessing Complete.")
    
    return(test_px, val_px, train_px)

def balanced_pix_data(landsat_datasets, lc_labels, canopy_labels, tile_size, tile_list, 
                           clean_pixels_count, class_count, count_per_class, class_dict, buffer_pix=1):
    # gets shuffled and balanced pixels data ready for ingestion viz and scikit learn
    
    print("Beginning balanced data creation.")

    pixels = make_clean_pix(tile_list, tile_size, landsat_datasets,lc_labels, canopy_labels, 
                                       clean_pixels_count, buffer_pix=buffer_pix)
    
    print("Clean pix generated, starting generator.")
   
    w_tile_gen = rnn_tiles.rnn_tile_gen(landsat_datasets, lc_labels, canopy_labels, tile_size, class_count)
    w_generator = w_tile_gen.tile_generator(pixels, batch_size=1, flatten=True, canopy=True)
    
    print("Iterating through data and clipping for balance.")

    class_count_dict = {}
    for key in class_dict:
        class_count_dict[key] = 0       

    count = 0
    sk_data = []
    sk_labels = []
    while count < len(pixels):
            image_b, label_b = next(w_generator)
            lc_class = np.argmax(label_b['landcover'])
            if class_count_dict[lc_class] < count_per_class:
                sk_data.append(image_b['rnn_input'].flatten())
                sk_labels.append([lc_class, label_b['canopy']])
                class_count_dict[lc_class] += 1
            count+=1
       
    print("Processing Complete.")
    
    return(np.array(sk_data), np.array(sk_labels), class_count_dict)

def all_pix_data(landsat_datasets, lc_labels, canopy_labels, tile_list, class_count, row_start, row_end):
    
    print("Beginning data creation.")
    
    pixels = make_pixels(1, tile_list, shuffle=False)[row_start:row_end]
    
    print("Pix generated, starting generator.")
   
    w_tile_gen = rnn_tiles.rnn_tile_gen(landsat_datasets, lc_labels, canopy_labels, 1, class_count)
    w_generator = w_tile_gen.tile_generator(pixels, batch_size=1, flatten=True, canopy=True)
    
    count = 0
    sk_data = []
    sk_labels = []
    while count < len(pixels):
            image_b, label_b = next(w_generator)
            lc_class = np.argmax(label_b['landcover'])        
            sk_data.append(image_b['rnn_input'].flatten())
            sk_labels.append([lc_class, label_b['canopy']])
            count+=1
       
    print("Processing Complete.")
    
    return(np.array(sk_data), np.array(sk_labels), np.array(pixels))

