

from setuptools import setup
from distutils.extension import Extension
import os
import os.path
import sys
from ctypes.util import find_library    # Useful function for findings libs (cross platform too)
import distutils.sysconfig
import distutils.ccompiler
import glob
import tempfile
import shutil
from textwrap import dedent
import distutils.sysconfig
import distutils.ccompiler
import setuptools.command.install
from distutils.errors import CompileError, LinkError
import re


def touch(fname, times=None):
    with open(fname, 'a'):
        os.utime(fname, times)


def get_header_definition(define, header, include_dirs):
    """
    Pull a #define out of a header file using the preprocessor
    """

    header_code = dedent("""
    #include <HEADER_ARG>

    #define DELIMIT(x) ;;;;;XSTR(x);;;;;
    #define XSTR(x) STR(x)
    #define STR(x) #x

    DELIMIT(DEFINE_ARG)

    """)

    header_code = header_code.replace("HEADER_ARG", header)
    header_code = header_code.replace("DEFINE_ARG", define)


    compiler = distutils.ccompiler.new_compiler()
    distutils.sysconfig.customize_compiler(compiler)
    compiler.set_include_dirs(include_dirs)
    tmp_dir = tempfile.mkdtemp(prefix='tmp_def_get_')
    file_name = os.path.join(tmp_dir, 'def_get.cpp')
    pre_out = os.path.join(tmp_dir, 'pre_out.l')
    with open(file_name, 'w') as fp:
        fp.write(header_code)

    find = None
    try:
        compiler.preprocess(file_name, output_file = pre_out)
        with open(pre_out, 'r') as f:
            result = f.read()
        find = re.search(r';;;;;"([^;"]*)";;;;;', result).group(1)
    except CompileError:
        sys.exit("Got an error trying to access " + header + ", is this library installed?")
    finally:
        shutil.rmtree(tmp_dir)

    return find



def check_gmp_function(hdirs, ldirs):
    """
    Check that gmp has mpn_sqr
    Thanks to Anthon on Stack Overflow
    http://stackoverflow.com/questions/28843765/setup-py-check-if-non-python-library-dependency-exists/
    Modified from his reply
    """

    libraries = ['gmp']

    # write a temporary .c file to compile
    c_code = dedent("""
    #include <gmp.h>

    int main(int argc, char* argv[])
    {
        mpn_sqr(0, 0, 1);
        return 0;
    }
    """)
    tmp_dir = tempfile.mkdtemp(prefix = 'tmp_gmp_')
    bin_file_name = os.path.join(tmp_dir, 'test_gmp')
    file_name = bin_file_name + '.c'
    with open(file_name, 'w') as fp:
        fp.write(c_code)

    # and try to compile it
    compiler = distutils.ccompiler.new_compiler()
    assert isinstance(compiler, distutils.ccompiler.CCompiler)
    distutils.sysconfig.customize_compiler(compiler)
    compiler.set_include_dirs(hdirs)
    compiler.set_library_dirs(ldirs)

    try:
        compiler.link_executable(
            compiler.compile([file_name]),
            bin_file_name,
            libraries=libraries,
        )
    except CompileError:
        print('libgmp compile error')
        ret_val = False
    except LinkError:
        print('libgmp link error')
        ret_val = False
    else:
        ret_val = True
    shutil.rmtree(tmp_dir)
    return ret_val



def check_function(function, header, link_against, ccompiler):
    """
    Similar to has_function in ccompiler, but this works regardless of arguments
    It assigns the function pointer to a void pointer
    Requires a C compiler instance augmented with include and library paths
    """

    code = dedent("""
    #include <HEADER_GOES_HERE>

    int main(){
    void *p __attribute__ ((unused)) = (void*)FUNCTION_GOES_HERE;
    }
    """)

    code=code.replace("HEADER_GOES_HERE", header)
    code=code.replace("FUNCTION_GOES_HERE", function)

    tmp_dir = tempfile.mkdtemp(prefix = 'tmp_fn_')
    bin_file_name = os.path.join(tmp_dir, 'test_fn')
    file_name = bin_file_name + '.cpp'
    with open(file_name, 'w') as fp:
        fp.write(code)

    ret = True
    try:
        ccompiler.link_executable(
            ccompiler.compile([file_name]),
            bin_file_name,
            libraries=[link_against]
        )
    except CompileError:
        print function + " compiler error"
        ret= False
    except LinkError:
        print function + " linker error"
        ret = False
    finally:
        shutil.rmtree(tmp_dir)

    return ret


# Find all the header and library paths
# At least the ones relevant to CGAL
def get_all_paths():
    def path_split(path_string):
        if os.name=='nt':
            sep = ';'
        else:
            sep = ':'
        return path_string.split(sep)

    def environ_path(environ_var):
        if environ_var in os.environ:
            return path_split(os.environ[environ_var])
        else:
            return []

    header_paths, library_paths = [], []
    compiler = distutils.ccompiler.new_compiler()
    distutils.sysconfig.customize_compiler(compiler)

    # Get paths from environment variables
    # These need to go first
    if os.name=='nt':
        # Our only hope is that they've set the %CGAL_DIR% var
        # The cgal installer does this
        cgal_dir = os.environ.get("CGAL_DIR")
        if cgal_dir is not None:
            header_paths.append(os.path.join(cgal_dir, "include"))
            library_paths.append(os.path.join(cgal_dir, "lib"))
            library_paths.append(os.path.join(cgal_dir, "bin"))
    else:
        for hvar in ['CPATH',
                    'C_INCLUDE_PATH',
                    'CPLUS_INCLUDE_PATH']:
            header_paths += environ_path(hvar)
        for lvar in ['LD_LIBRARY_PATH',
                     'LIBRARY_PATH']:
            library_paths += environ_path(lvar)

    
    header_paths.append("/usr/local/include")
    library_paths.append("/usr/local/lib")
    library_paths.append("/usr/local/lib64")
    header_paths.append("/usr/include")
    library_paths.append("/usr/lib")
    library_paths.append("/usr/lib64")

    # Only UnixCompiler has this attribute at the moment
    # It contains all the arguments passed to the compiler, some of which are paths
    if hasattr(compiler,'compiler_so'):
        for arg_or_path in compiler.compiler_so:
            if arg_or_path.startswith("-I/"):
                header_paths.append(arg_or_path[2:])
            if arg_or_path.startswith("-L/"):
                library_paths.append(arg_or_path[2:])


    header_paths = filter(os.path.isdir, header_paths)
    library_paths = filter(os.path.isdir, library_paths)
    return header_paths, library_paths


# Find a file inside the header/library search paths
# Case insensitive
def find_in_paths(search_paths, search):
    for path in search_paths:
        for file in os.listdir(path):
            if file.lower() == search.lower():
                return os.path.join(path, file)
    return None

# This is the directory where the CMake build puts everything by default
OUT_DIR = os.path.abspath('build-python')

PACKAGE_DIR = os.path.join(OUT_DIR,"CGAL")

#Create the package directory structure if it doesn't already exist
#The existing Cmake install might already have made it
if not os.path.exists(PACKAGE_DIR):
    os.makedirs(PACKAGE_DIR)

initpy = os.path.join(PACKAGE_DIR, "__init__.py")
if not os.path.exists(initpy):
    touch(initpy)

# The subdirectories in SWIG_CGAL which contain swig interface files
CGAL_modules = [
    "Kernel",
    "AABB_tree",
    "Alpha_shape_2",
    "Box_intersection_d",
    "Convex_hull_2",
    "HalfedgeDS",
    "Interpolation",
    "Mesh_2",
    "Mesh_3",
    "Point_set_processing_3",       # needs eigen3
    "Polyhedron_3",
    "Spatial_searching",
    "Surface_mesher",               # needs imageio components (CGAL was built with imageio)
    "Triangulation_2",
    "Triangulation_3",
    "Voronoi_diagram_2"
]



INCLUDE_DIRS = ["./","SWIG_CGAL/AABB_tree/include"]
MACROS = ['CGAL_USE_GMP', 'CGAL_USE_MPFR', 'CGAL_USE_ZLIB', 'CGAL_Kernel_cpp_EXPORTS']
LINKER_LIBS = ['CGAL', 'gmp', 'mpfr']
MACROS = [(s, None) for s in MACROS]
HEADER_PATHS, LIBRARY_PATHS = get_all_paths()
CGAL_HEADER_PATH  = find_in_paths(HEADER_PATHS, 'cgal')

compiler = distutils.ccompiler.new_compiler()
distutils.sysconfig.customize_compiler(compiler)
compiler.set_include_dirs(HEADER_PATHS)
compiler.set_library_dirs(LIBRARY_PATHS)

# Print out all the error messages at once, instead of exiting immediately
# That way, users can instantly see how screwed they are by getting all the errors at once
dependencies_ok = True

#For some reason it's boost_thread-mt on some systems and boost_thread on others
#Both are the same
BOOST_THREAD_NAME = None
for try_name in ["boost_thread-mt","boost_thread"]:
        if compiler.find_library_file(LIBRARY_PATHS, try_name) is not None:
            BOOST_THREAD_NAME = try_name

if BOOST_THREAD_NAME is None:
    sys.exit("You are missing boost_thread")


for library_dep in ['gmp', 'mpfr', 'CGAL', 'boost_thread-mt']:
    if compiler.find_library_file(LIBRARY_PATHS, library_dep) is None:
        sys.stderr.write("You are missing the {0} library\n".format(library_dep))
        dependencies_ok = False

if not dependencies_ok:
    sys.exit(-1)

# Function, header, library to link against
function_dependencies = [
    ("mpn_sqr", "gmp.h", "gmp"),
    ("boost::detail::set_tss_data", "boost/thread/tss.hpp", "boost_thread-mt"),
]

for function, header, lib in function_dependencies:
    if not check_function(function, header, lib, compiler):
        sys.stderr.write("You are missing the function {0} defined in {1}\n".format(function, header))
        dependencies_ok = False

gmp_version = get_header_definition('__GNU_MP_VERSION', 'gmp.h', HEADER_PATHS)
if gmp_version is None or int(gmp_version) < 5:
    sys.stderr.write("Your GMP library is really old, you should update it\n")
    dependencies_ok = False

boost_ver = get_header_definition('BOOST_VERSION', 'boost/version.hpp', HEADER_PATHS)
if boost_ver is None or int(boost_ver) <= 104200:
    # Had some issues compiling with an old boost
    sys.stderr.write("WARNING: I would highly recommend updating your boost library\n")

if not dependencies_ok:
    sys.exit(-1)


#Make some guesses as to where that CGALConfig.make file is
CGAL_CONFIG_SEARCH = [
    os.environ.get("CGAL_DIR", ""),
    find_in_paths(LIBRARY_PATHS, 'cgal') or ""
]
CGAL_CONFIG_SEARCH = filter(os.path.isdir, CGAL_CONFIG_SEARCH)
CGAL_CONFIG_SEARCH += HEADER_PATHS


# Use CGALConfig.make to see if it was built with imageio
WITH_IMAGEIO = False
cgal_config = find_in_paths(CGAL_CONFIG_SEARCH, "CGALConfig.cmake")
if cgal_config is not None and os.path.isfile(cgal_config):
    file = open(cgal_config)
    for line in file:
        if line.replace(" ","").replace('"',' ').lower().startswith('set(with_cgal_imageio on'):
            WITH_IMAGEIO = True
            print "Found image IO"
            LINKER_LIBS.append('CGAL_ImageIO')
            break
else:
    sys.stderr.write("Couldn't find CGALConfig.cmake\n")

if not WITH_IMAGEIO:
    sys.stderr.write("ImageIO is not installed, skipping Surface_mesher\n")
    CGAL_modules.remove("Surface_mesher")


EIGEN3_PATH = find_in_paths(HEADER_PATHS, 'eigen3')
if EIGEN3_PATH is None:
    sys.stderr.write("No Eigen3 found, skipping Point_set_processing_3\n")
    CGAL_modules.remove("Point_set_processing_3")
else:
    # We have eigen3, enable it
    # It is stil possible that they've installed Eigen3 but didn't build it into CGAL
    # In that case...no idea
    INCLUDE_DIRS.append(EIGEN3_PATH)
    MACROS.append(('CGAL_EIGEN3_ENABLED', None))


# Translate the names of folders into actual Extension instances
extensions = []
for mod_name in CGAL_modules:
    macros = MACROS[:]
    macros.append(("_CGAL_{0}_EXPORTS".format(mod_name), None))
    source_list = ["SWIG_CGAL/{0}/CGAL_{0}.i".format(mod_name)]
    source_list += glob.glob("SWIG_CGAL/{0}/*.cpp".format(mod_name))
    source_list = filter(lambda s: not s.endswith('_wrap.cpp'), source_list)
    e = Extension("_CGAL_" + mod_name,
                  sources=source_list,
                  swig_opts=["-c++","-outdir",PACKAGE_DIR,"-DSWIG_CGAL_{0}_MODULE".format(mod_name)],     # -DSWIG_CGAL_Surface_mesher_MODULE
                  libraries=['CGAL', 'gmp', 'mpfr'],
                  define_macros=macros,
                  include_dirs=INCLUDE_DIRS + HEADER_PATHS,
                  library_dirs=LIBRARY_PATHS,
                  extra_compile_args=["-fPIC"])

    extensions.append(e)

class Build_ext_first(setuptools.command.install.install):
    def run(self):
        self.run_command("build_ext")
        return setuptools.command.install.install.run(self)


setup(
    name="cgal-bindings",
    author_email="sciencectn@gmail.com",    # author of the setup.py? or the whole library?
    description="Uses SWIG to generate bindings so you can use certain CGAL classes in Python.",
    packages=['CGAL'],
    ext_package='CGAL',
    ext_modules = extensions,
    package_dir = {'': 'build-python'},
    cmdclass = {'install' : Build_ext_first}
)

