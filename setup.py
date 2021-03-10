"""Package setup file for motionEye client library."""

import setuptools

with open("README.md") as fh:
    long_description = fh.read()

setuptools.setup(
    name="motioneye-client",
    version="0.0.1",
    author="Dermot Duffy",
    author_email="dermot.duffy@gmail.com",
    description="motionEye client library Python Package",
    include_package_data=True,
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="motioneye",
    url="https://github.com/dermotduffy/motioneye-client",
    package_data={"motioneye-client": ["py.typed"]},
    packages=setuptools.find_packages(exclude=["tests", "tests.*"]),
    platforms="any",
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Home Automation",
    ],
    python_requires=">=3.7",
    zip_safe=False,  # Required for py.typed.
)
