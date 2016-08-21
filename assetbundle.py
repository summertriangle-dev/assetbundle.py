#!/usr/bin/python3
# -!- coding: utf-8 -!-
#
# Copyright 2016 Hector Martin <marcan@marcan.st>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This version of decode.py adds an unwrapping chain, allowing for
# headers, compression, encryption, etc. to be removed before the
# actual asset stream is passed to the decoder. Additionally, the
# decoder now yields a list of stubs that can be called to load
# the referred object, potentially saving time and space.

import struct, sys, os
import ctypes
import lz4
import io
import lzma
from collections import defaultdict, namedtuple
import itertools
import functools

promised_file_t = namedtuple("promised_file_t", ("typename", "pathid", "fulfill"))
promised_file_t.__str__ = lambda x: "{0}(typename={1}, pathID={2}, fulfill=<redacted>)".format(
    x.__class__.__name__, repr(x.typename), repr(x.pathid))
xrange = range

baseStrings = defaultdict(lambda: "TypeUnknown")
baseStrings.update({
    0:"AABB",
    5:"AnimationClip",
    19:"AnimationCurve",
    49:"Array",
    55:"Base",
    60:"BitField",
    76:"bool",
    81:"char",
    86:"ColorRGBA",
    106:"data",
    138:"FastPropertyName",
    155:"first",
    161:"float",
    167:"Font",
    172:"GameObject",
    183:"Generic Mono",
    208:"GUID",
    222:"int",
    241:"map",
    245:"Matrix4x4f",
    262:"NavMeshSettings",
    263:"MonoBehaviour",
    277:"MonoScript",
    299:"m_Curve",
    349:"m_Enabled",
    374:"m_GameObject",
    427:"m_Name",
    490:"m_Script",
    519:"m_Type",
    526:"m_Version",
    543:"pair",
    548:"PPtr<Component>",
    564:"PPtr<GameObject>",
    581:"PPtr<Material>",
    616:"PPtr<MonoScript>",
    633:"PPtr<Object>",
    688:"PPtr<Texture>",
    702:"PPtr<Texture2D>",
    718:"PPtr<Transform>",
    741:"Quaternionf",
    753:"Rectf",
    778:"second",
    795:"size",
    800:"SInt16",
    814:"int64",
    840:"string",
    847:"TextAsset",
    874:"Texture2D",
    884:"Transform",
    894:"TypelessData",
    907:"UInt16",
    928:"UInt8",
    934:"unsigned int",
    981:"vector",
    988:"Vector2f",
    997:"Vector3f",
    1006:"Vector4f",
})

class Stream(object):
    """ the stream reader from ksar """
    def __init__(self, file):
        self.f = file

    def tell(self):
        return self.f.tell()

    def seek(self, at, where=os.SEEK_SET):
        return self.f.seek(at, where)

    def skip(self, off):
        self.seek(off, os.SEEK_CUR)

    def read(self, cnt):
        return self.bytes(cnt)

    def align(self, n):
        self.seek((self.tell() + n - 1) & ~(n - 1))

    def read_str(self):
        return self.string0()

    def readfunc(fmt):
        a = struct.Struct(fmt)
        b = a.size
        def f(f, at=None):
            if at is not None:
                back = f.tell()
                f.seek(at)
                d = a.unpack(f.read(b))[0]
                f.seek(back)
                return d
            else:
                return a.unpack(f.read(b))[0]
        return f

    def latebinder(f):
        return lambda s: f(s.f)

    be_int8_t    = latebinder(readfunc(">b"))
    be_uint8_t   = latebinder(readfunc(">B"))
    be_int16_t   = latebinder(readfunc(">h"))
    be_uint16_t  = latebinder(readfunc(">H"))
    be_int32_t   = latebinder(readfunc(">i"))
    be_uint32_t  = latebinder(readfunc(">I"))
    be_int64_t   = latebinder(readfunc(">q"))
    be_uint64_t  = latebinder(readfunc(">Q"))
    be_float32_t = latebinder(readfunc(">f"))
    be_float64_t = latebinder(readfunc(">d"))

    int8_t    = latebinder(readfunc("<b"))
    uint8_t   = latebinder(readfunc("<B"))
    int16_t   = latebinder(readfunc("<h"))
    uint16_t  = latebinder(readfunc("<H"))
    int32_t   = latebinder(readfunc("<i"))
    uint32_t  = latebinder(readfunc("<I"))
    int64_t   = latebinder(readfunc("<q"))
    uint64_t  = latebinder(readfunc("<Q"))
    float32_t = latebinder(readfunc("<f"))
    float64_t = latebinder(readfunc("<d"))

    def struct(self, struct, at=None):
        if at is not None:
            back = self.f.tell()
            self.f.seek(at)
            d = self.struct(struct)
            self.f.seek(back)
            return d

        return struct.unpack(self.f.read(struct.size))

    def structs(self, struct, n, at=None):
        if at is not None:
            back = self.f.tell()
            self.f.seek(at)
            d = self.structs(struct, n)
            self.f.seek(back)
            return d

        return [self.struct(struct) for _ in range(n)]

    def bytes(self, size, at=None):
        if at is not None:
            back = self.f.tell()
            self.f.seek(at)
            d = self.bytes(size)
            self.f.seek(back)
            return d

        return self.f.read(size)

    def string(self, prefixlen=4, at=None):
        if at is not None:
            back = self.f.tell()
            self.f.seek(at)
            d = self.string(prefixlen)
            self.f.seek(back)
            return d

        prefixgetter = {
            1: self.uint8_t,
            2: self.uint16_t,
            4: self.uint32_t,
            8: self.uint64_t,
        }

        string_length = prefixgetter[prefixlen]()
        string. self.f.read(string_length)
        return string.decode("utf8")

    def string0(self, at=None):
        if at is not None:
            back = self.f.tell()
            self.f.seek(at)
            d = self.string0()
            self.f.seek(back)
            return d

        bk = self.f.tell()
        tl = 0
        sr = []
        while 1:
            b = self.f.read(16)
            tl += len(b)

            if len(b) == 0:
                raise Exception("EOF")

            for c in b:
                if c != 0:
                    sr.append(c)
                else:
                    break
            else:
                continue
            break
        string = bytes(sr)
        self.f.seek(bk + len(string) + 1)
        return string.decode("utf8")

class Def(object):
    TYPEMAP = {
        "int": "<i",
        "int64": "<q",
        "char": "<1s",
        "bool": "<B",
        "float": "<f"
    }
    def __init__(self, name, type_name, size, flags, array=False):
        self.children = []
        self.name = name
        self.type_name = type_name
        self.size = size
        self.flags = flags
        self.array = array

    def read(self, s):
        if self.array:
            #print "a", self.name
            size = self.children[0].read(s)
            assert size < 10000000
            if self.children[1].type_name in ("UInt8","char"):
                #print "s", size
                return s.read(size)
            else:
                return [self.children[1].read(s) for i in xrange(size)]
        elif self.children:
            #print "o", self.name
            v = {}
            for i in self.children:
                v[i.name] = i.read(s)
            if len(v) == 1 and self.type_name == "string":
                return v["Array"]
            return v
        else:
            x = s.tell()
            s.align(min(self.size,4))
            d = s.read(self.size)
            if self.type_name in self.TYPEMAP:
                d = struct.unpack(self.TYPEMAP[self.type_name], d)[0]
            #print hex(x), self.name, self.type_name, repr(d)
            return d

    def __getitem__(self, i):
        return self.children[i]

    def append(self, d):
        self.children.append(d)

class Asset(object):
    def __init__(self, stream):
        self.s = stream

        # self.s.seek(0x70)
        self.off = self.s.tell()

        self.table_size, self.data_end, self.file_gen, self.data_offset = struct.unpack(">IIII", self.s.read(16))
        self.s.read(4)
        self.version = self.s.read_str()
        self.platform = struct.unpack("<I", self.s.read(4))
        self.defs = self.decode_defs()
        self.objs = self.decode_data()

    def fulfill_promise(self, off, t1):
        self.s.seek(off + self.data_offset + self.off)
        try:
            return self.defs[t1].read(self.s)
        except AssertionError as e:
            raise ValueError("read failed: asserted " + str(e))

    def decode_defs(self):
        are_defs, count = struct.unpack("<BI", self.s.read(5))
        return dict(self.decode_attrtab() for i in xrange(count))

    def decode_data(self):
        count = struct.unpack("<I", self.s.read(4))[0]
        objs = []
        assert count < 2048
        for i in xrange(count):
            self.s.align(4)
            pathId, off, size, t1, t2, unk = struct.unpack("<QIIIH2xB", self.s.read(25))

            p = functools.partial(self.fulfill_promise, off, t1)
            objs.append(promised_file_t(self.defs[t1].type_name, hex(pathId), p))
        return objs

    def decode_attrtab(self):
        code, = struct.unpack("<I", self.s.read(4))
        if code == 0xFFFFFFFF:
            ident, attr_cnt, stab_len = struct.unpack("<32sII", self.s.read(40))
        else:
            ident, attr_cnt, stab_len = struct.unpack("<16sII", self.s.read(24))
        #print "%08x %s" % (code, ident.encode("hex"))
        attrs = self.s.read(attr_cnt*24)
        stab = self.s.read(stab_len)

        defs = []
        assert attr_cnt < 2048
        for i in xrange(attr_cnt):
            a1, a2, level, a4, type_off, name_off, size, idx, flags = struct.unpack("<BBBBIIIII", attrs[i*24:i*24+24])
            # print(a1, a2, level, a4, type_off, name_off, size, idx, flags)
            if name_off & 0x80000000:
                name = baseStrings[name_off & 0x7fffffff]
            else:
                name = stab[name_off:].split(b"\0")[0].decode("utf8")
            if type_off & 0x80000000:
                type_name = baseStrings[type_off & 0x7fffffff]
            else:
                type_name = stab[type_off:].split(b"\0")[0].decode("utf8")
            d = defs
            assert level < 32, str(level)
            for i in range(level):
                d = d[-1]
            if size == 0xffffffff:
                size = None
            # print("def", name, type_name, size, flags, a4)
            d.append(Def(name, type_name, size, flags, array=bool(a4)))
            #print "%2x %2x %2x %20s %8x %8x %2d: %s%s" % (a1, a2, a4, type_name, size or -1, flags, idx, "  " * level, name)

        assert len(defs) == 1
        return code, defs[0]

### WRAPPING

libhotwater = None
libahff = None

def hot_water_unwrap(name, stream):
    magic = stream.read(5)
    stream.seek(0)

    # we can take advantage of the fact that valid cleartext starts with "Unity",
    # therefore a valid ciphertext will start with the encrypted value
    if magic == b"\x7E\x08\x9D\x2F\xC0":
        if libhotwater is None:
            print("warning: this looks like a valid stream (yes i know encrypted data "
                  "is supposed to look random but i can tell), but libhotwater is "
                  "not initialized. if you are using this as a library, you must call "
                  "initialize_libhotwater manually.")
            raise ContinueUnwrapping(name, stream)

        b = stream.read()
        libhotwater.hot_water_decrypt_buffer(
            None, 0, 0, 0, b, len(b))

        stream.close()
        raise ContinueUnwrapping(name, io.BytesIO(b))
    else:
        raise ContinueUnwrapping(name, stream)

def unityfs_unwrap(name, fd):
    magic = fd.read(8)
    fd.seek(0)

    if magic != b"UnityFS\x00":
        raise ContinueUnwrapping(name, fd)

    stream = Stream(fd)
    stream.seek(9, 1)

    sv = stream.be_uint32_t()
    creator, rev = stream.string0(), stream.string0()
    filesize, cdhsize, dhsize, flg = stream.struct(struct.Struct(">QIII"))

    hsize = stream.tell()

    if flg & 0x80 == 0:
        hsize += cdhsize
    else:
        stream.seek(filesize - cdhsize)

    dh = stream.bytes(cdhsize)

    ctype = flg & 0x3f
    if ctype == 3:
        dhstr = Stream(io.BytesIO(lz4.loads(struct.pack("<I", dhsize) + dh)))
    # TODO lzma
    else:
        dhstr = Stream(io.BytesIO(dh))

    dhstr.skip(16)
    blk_cnt = dhstr.be_uint32_t()
    blk_struct = struct.Struct(">IIH")
    blockdefs = dhstr.structs(blk_struct, blk_cnt)

    fl_cnt = dhstr.be_uint32_t()
    file_struct = struct.Struct(">QQI")

    for x in range(fl_cnt):
        filedef = dhstr.struct(file_struct)
        dhstr.string0()
        blockdef = blockdefs[x]

        fd.seek(hsize + filedef[0])

        ctype_file = blockdef[2] & 0x3f
        if ctype_file == 1:
            fixed_lz_stream = io.BytesIO()
            fixed_lz_stream.write(fd.read(5))
            # we do know the right file size, but lzma barfs when we put it here
            # using the unknown size constant seems to work
            fixed_lz_stream.write(b"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF")
            fixed_lz_stream.write(fd.read(blockdef[1] - 5))
            fixed_lz_stream.seek(0)

            with lzma.open(fixed_lz_stream, "rb", format=lzma.FORMAT_ALONE) as s:
                yield Asset(Stream(io.BytesIO(s.read())))
        # TODO lz4
        else:
            yield Asset(Stream(io.BytesIO(fd.read(filedef[1]))))

    fd.close()

def unityraw_unwrap(name, fd):
    magic = fd.read(9)

    if magic != "UnityRaw\x00":
        fd.seek(0)
        raise ContinueUnwrapping(name, fd)
    else:
        # TODO parse header
        fd.seek(0x70)
        yield Asset(Stream(fd))

    fd.close()

UnwrapperChain = [
    hot_water_unwrap,
    # TODO: add a function for the starlight stage LZ4 files
    unityfs_unwrap,
    unityraw_unwrap,
]

class ContinueUnwrapping(Exception):
    def __init__(self, name, fd):
        self.name = name
        self.fd = fd

def open_bundle(filename):
    fd = open(filename, "rb")

    iterator = None

    for unwrap in UnwrapperChain:
        try:
            return list(itertools.chain(*(x.objs for x in unwrap(filename, fd))))
        except ContinueUnwrapping as e:
            filename = e.name
            fd = e.fd
            continue
    else:
        raise ValueError("Couldn't unwrap the file at all")


def save_image(tex, libahff, name):
    data = tex["image data"]
    libahff.ahff_encode_texdata(tex["m_TextureFormat"], tex["m_Width"], tex["m_Height"],
        len(data), data, name.encode("utf8"))

def initialize_libahff():
    global libahff

    libahff = ctypes.cdll.LoadLibrary(
        os.path.join(os.path.dirname(__file__), "libahff.dylib"))
    libahff.ahff_encode_texdata.argtypes = [
        ctypes.c_int,     # int fmt,
        ctypes.c_int,     # int width,
        ctypes.c_int,     # int height,
        ctypes.c_size_t,  # size_t len,
        ctypes.c_char_p,  # const uint8_t *data,
        ctypes.c_char_p]  # const char *out_path
    libahff.ahff_encode_texdata.restype = ctypes.c_int

def initialize_libhotwater():
    global libhotwater

    libhotwater = ctypes.cdll.LoadLibrary(
        os.path.join(os.path.dirname(__file__), "libhotwater.dylib"))
    libhotwater.hot_water_decrypt_buffer.argtypes = [
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32]
    libhotwater.hot_water_decrypt_buffer.restype = None

if __name__ == "__main__":
    try:
        initialize_libahff()
    except OSError as e:
        print("warning: libahff not initialized,", str(e))

    try:
        initialize_libhotwater()
    except OSError as e:
        print("warning: libhotwater not initialized,", str(e))

    assets = open_bundle(sys.argv[1])

    for o in assets:
        print(o)
        # if o.typename == "TextAsset":
        #     o = o.fulfill()
        #     with open(o["m_Name"] + b".txt", "wb") as outfi:
        #         outfi.write(o["m_Script"])
        if o.typename == "Texture2D":
            o = o.fulfill()
            oname = (os.path.basename(sys.argv[1]) + "_" + o["m_Name"].decode("utf8")).replace("/", "_") + ".png"
            save_image(o, libahff, oname)
            print("  ^ written to", oname)
