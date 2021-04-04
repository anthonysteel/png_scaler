import zlib
import struct

def reduce_byte_list(data):
    return reduce(lambda x,y: x+y, data)

class chunk:
    def __init__(self, length, chunk_type, crc, data):
        self.length = length
        self.chunk_type = chunk_type
        self.crc = crc
        self.data = data
    def pack(self):
        if self.chunk_type == 'IDAT':
            return struct.pack(">I", self.length)+\
               bytes(self.chunk_type)+\
               zlib.compress(reduce_byte_list(self.data))+\
               struct.pack(">I", self.crc)
        if self.chunk_type == 'IEND':
            return struct.pack(">I", self.length)+\
               bytes(self.chunk_type)+struct.pack(">I", self.crc)
        return struct.pack(">I", self.length)+\
               bytes(self.chunk_type)+\
               reduce_byte_list(self.data)+struct.pack(">I", self.crc)

class png:
    def __init__(self, width, height, bit_depth, color_type,\
                       compression_method, filter_method, interlace_method,\
                       pixels_per_unit_x_axis, pixels_per_unit_y_axis,\
                       unit_specifier):
        self.width = width
        self.height = height
        self.bit_depth = bit_depth
        self.color_type = color_type
        self.compression_method = compression_method
        self.filter_method = filter_method
        self.interlace_method = interlace_method
        self.pixels_per_unit_x_axis = pixels_per_unit_x_axis
        self.pixels_per_unit_y_axis = pixels_per_unit_y_axis
        self.unit_specifier = unit_specifier
        

def is_png(file_signature):
    return file_signature == ['\x89', 'P', 'N', 'G', '\r', '\n', '\x1a', '\n']

'''
Helper functions for retrieving bytes in various formats
from PNG file
'''
def get_list_from_bytes(f, number_of_bytes):
    return list(bytes(f.read(number_of_bytes)))

def get_int_from_bytes(f, number_of_bytes):
    return int(f.read(number_of_bytes).encode("hex"), 16)

def get_string_from_bytes(f, number_of_bytes):
    return f.read(number_of_bytes)

def get_int_from_byte_list(byte_list):
    return int(reduce(lambda x,y: x+y, byte_list).encode("hex"), 16)

def get_bytes_from_list(byte_list):
    return reduce(lambda x,y: x+y, byte_list)

def get_chunk(f):
    length = get_int_from_bytes(f, 4)
    if length > 2**31-1:
        print("Error: length of chunk is too large (exceeds 2**31-1)")
        return -1
    chunk_type = get_string_from_bytes(f, 4)
    data = get_list_from_bytes(f, length)
    crc = get_int_from_bytes(f, 4)
    return chunk(length, chunk_type, crc, data)

def get_all_chunks(f):
    chunks = {}
    c = get_chunk(f)
    while c.chunk_type != 'IEND':
        chunks[c.chunk_type] = c
        c = get_chunk(f)
    chunks[c.chunk_type] = c
    return chunks

def get_scanlines(data, height, width):
    scanline_width = width * 3 + 1
    scanlines = []
    for i in range(0, height):
        scanlines.append(list(data[i*scanline_width:(i+1)*scanline_width]))
    return scanlines

'''
Parsing functions for chunks
'''
def parse_ihdr(data):
    width = get_int_from_byte_list(data[0:4])
    height = get_int_from_byte_list(data[4:8])
    bit_depth = get_int_from_byte_list(data[8:9])
    color_type = get_int_from_byte_list(data[9])
    compression_method = get_int_from_byte_list(data[10])
    filter_method = get_int_from_byte_list(data[11])
    interlace_method = get_int_from_byte_list(data[12])
    return (width, height, bit_depth, color_type, compression_method,\
            filter_method, interlace_method)

def parse_phys(data):
    pixels_per_unit_x_axis = get_int_from_byte_list(data[0:4])
    pixels_per_unit_y_axis = get_int_from_byte_list(data[4:8])
    unit_specifier = get_int_from_byte_list(data[8])
    return (pixels_per_unit_x_axis, pixels_per_unit_y_axis, unit_specifier)

def reconstruct(x, a):
    return (x + a) & 0xff

def reconstruct_pixel(pixel1, pixel2):
    return [reconstruct(pixel1[0], pixel2[0]),\
            reconstruct(pixel1[1], pixel2[1]),\
            reconstruct(pixel1[2], pixel2[2])]

def unfilter(scanline):
    pixels = []
    for i in range(len(scanline)):
        previous_pixel = [0, 0, 0]
        for j in range(1, len(scanline[i]), 3):
            pixel = scanline[i][j:j+3]
            pixels.append(reconstruct_pixel(pixel, previous_pixel))
            previous_pixel = reconstruct_pixel(pixel, previous_pixel)
    return pixels

def get_pixels(filename):
    with open(filename) as f:
        file_signature = get_list_from_bytes(f, 8)
        if is_png(file_signature):
            chunks = get_all_chunks(f)
            idat_chunk = chunks['IDAT']
            phys_chunk = chunks['pHYs']
            ihdr_chunk = chunks['IHDR']
            iend_chunk = chunks['IEND']

            print(phys_chunk.length, phys_chunk.data, phys_chunk.chunk_type,\
                    phys_chunk.crc)
            
            width, height, bit_depth, color_type, compression_method,\
                filter_method, interlace_method = parse_ihdr(ihdr_chunk.data)
            uncompressed_data = list(zlib.decompress(\
                    get_bytes_from_list(idat_chunk.data)))
            decimal_data = [int(x.encode("hex"), 16) for x in uncompressed_data]
            scanlines = get_scanlines(decimal_data, height, width)
            pixels = unfilter(scanlines)
            return ihdr_chunk, iend_chunk, pixels 
        else:
            print("Error: file is not a PNG")

'''
Functions for converting units
'''
def inches_to_meters(inches):
    return inches / 39.37

'''
Functions for creating PNG file
'''
def create_checksum(data, tag):
    checksum = zlib.crc32(tag) & 0xffffffff
    return zlib.crc32(data, checksum) & 0xffffffff

def create_phys_chunk(pixels_per_unit_x_axis, pixels_per_unit_y_axis,\
                      unit_specifier):
    '''
    The `struct` package is being used to pack binary data. The `struct.pack`
    function requires format and the object to converted to binary.
    The options for format are here:
    https://docs.python.org/2/library/struct.html#format-characters
    Quick look:
        I, unsigned int, 4 bytes
        B, unsigned int, 1 byte
    '''

    print(pixels_per_unit_x_axis, pixels_per_unit_y_axis, unit_specifier) 
    length = 9 
    chunk_type = 'pHYs'
    data = list(struct.pack(">I", pixels_per_unit_x_axis)+\
                struct.pack(">I", pixels_per_unit_y_axis)+\
                struct.pack(">B", unit_specifier))
    crc = create_checksum(reduce_byte_list(data), chunk_type)
    return chunk(length, chunk_type, crc, data)

def create_data_chunk(pixels, pixel_width):
    print(len(pixels))
    scanline = []
    if len(pixels) < pixel_width:
       scanline = pixels 
    data = map(lambda x: struct.pack(">B", x),\
          [0]+reduce(lambda x,y: x+y, scanline))
    length = len(data)
    chunk_type = 'IDAT'
    crc = create_checksum(reduce_byte_list(data), chunk_type)
    return chunk(length, chunk_type, crc, data)

def main():
    ihdr_chunk, iend_chunk, pixels = get_pixels('simple_no_alpha.png')

    meters_per_pixel = 0.002 # m or 2mm
    pixels_per_meter = int(1/meters_per_pixel)
    
    canvas_width = inches_to_meters(8.5 - 1)
    canvas_height = inches_to_meters(11 - 1)

    pixel_width = int(canvas_width * pixels_per_meter)
    pixel_height = int(canvas_height * pixels_per_meter)

    width, height, bit_depth, color_type, compression_method,\
        filter_method, interlace_method = parse_ihdr(ihdr_chunk.data)

    file_signature = struct.pack(">B", 137)+\
                     struct.pack(">B", 80)+\
                     struct.pack(">B", 78)+\
                     struct.pack(">B", 71)+\
                     struct.pack(">B", 13)+\
                     struct.pack(">B", 10)+\
                     struct.pack(">B", 26)+\
                     struct.pack(">B", 10)
    ihdr_chunk.data[3] = struct.pack(">B", 6)
    ihdr_chunk.data[7] = struct.pack(">B", 1)
    print(ihdr_chunk.data)
    phys_chunk = create_phys_chunk(pixels_per_meter, pixels_per_meter, 1)
    idat_chunk = create_data_chunk(pixels, pixel_width)

    with open('simple_new.png', 'w') as f:
        f.write(file_signature)
        f.write(ihdr_chunk.pack())
        f.write(phys_chunk.pack())
        f.write(idat_chunk.pack())
        f.write(iend_chunk.pack())

if __name__ == '__main__':
    main()

    '''
    ihdr_chunk = get_chunk(f)
    phys_chunk = get_chunk(f)
    #idat_chunk = get_chunk(f)
    #iend_chunk = get_chunk(f)

    if ihdr_chunk.chunk_type != 'IHDR':
        print("Error: PNG is corrupted. IHDR did not immediately\
               follow file signature")

    width, height, bit_depth, color_type, compression_method,\
        filter_method, interlace_method = parse_ihdr(ihdr_chunk.data)

    print(phys_chunk.length)
    parse_phys(phys_chunk.data)
    pixels_per_unit_x_axis, pixels_per_unit_y_axis, unit_specifier =\
        parse_phys(phys_chunk.data)

    png_file = png(width, height, bit_depth, color_type,\
                   compression_method, filter_method, interlace_method,\
                   pixels_per_unit_x_axis, pixels_per_unit_x_axis,\
                   unit_specifier)
    '''
    #print(filter_method)
    #print(width, height, bit_depth, color_type)
    #print(idat_chunk.length)
    #uncompressed_data = list(zlib.decompress(\
    #        get_bytes_from_list(idat_chunk.data)))
