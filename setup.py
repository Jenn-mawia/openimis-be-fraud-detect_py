import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), "README.md")) as readme:
    README = readme.read()

os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name="openimis-be-fraud-detect",
    version="1.0.0",
    packages=find_packages(),
    include_package_data=True,
    license="GNU AGPL v3",
    description="AI-powered claims fraud detection module for openIMIS (Rules Engine + Isolation Forest).",
    long_description=README,
    url="https://openimis.org/",
    author="Lewis Munyi",
    author_email="lewis.ndwiga@strathmore.edu",
    install_requires=[
        "django",
        "djangorestframework",
        "graphene-django",
        "scikit-learn>=1.3",
        "joblib",
        "numpy",
        "pandas",
        "openimis-be-core",
        "openimis-be-claim",
    ],
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 3.2",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)
