from setuptools import setup

with open("README.md", "r") as rdme:
    desc = rdme.read()

setup(
    name = 'vasco',
    version = '0.2.0',
    url='https://gitlab.ia.forth.gr/smile/vasco/',
    author='Avinash Kumar',
    author_email='avialxee@gmail.com',
    description='VASCO: VLBI and SMILE source based CASA Optimizations.',
    py_modules = ["vasco"],
    package_dir={'':'src'},
    classifiers=["Programming Language :: Python :: 3",
                #  "Programming Language :: Python :: 3.6",
                #  "Programming Language :: Python :: 3.7",
                 "Programming Language :: Python :: 3.8",
                 "Programming Language :: Python :: 3.9",
                 "Programming Language :: Python :: 3.10",
                 "Programming Language :: Python :: 3.11",
                 "License :: OSI Approved :: BSD License",
                 "Intended Audience :: Science/Research",
                 ],
    long_description=desc,
    long_description_content_type = "text/markdown",
    install_requires=["astropy", "numpy", "ipython", "pyvirtualdisplay", "pandas", "scipy",
                      "scikit-learn", 'polars',
                      
                    #  "casaplotms", # start depreciation
                    #   "casatools",
                      "protobuf==3.20.3",
                      ],
    extras_require = {
        "all" : ['fitsio', 'casatools', 'casatasks', 'python-casacore'] , 
        "dev" : ["pytest>=3.7",
        ]
    },
     entry_points={ 
        "console_scripts": [
            "vasco=vasco:cli"
        ],
    },

)