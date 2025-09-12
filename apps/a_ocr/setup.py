import os
from setuptools import setup, find_packages

def parse_requirements():
    req_path = os.path.join(os.path.dirname(__file__), "..","..", "requirements.txt")
    with open(req_path, "r", encoding="utf-8") as f:
        return f.read().splitlines()
        
setup(
    name='dots_ocr',  
    version='1.0', 
    packages=find_packages(),  
    include_package_data=True,
    install_requires=parse_requirements(),
    description='dots.ocr: Multilingual Document Layout Parsing in one Vision-Language Model',
    url="https://github.com/rednote-hilab/dots.ocr",
    python_requires=">=3.10",
)