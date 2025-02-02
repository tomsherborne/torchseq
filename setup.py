import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="torchseq",
    version="2.3.1.dev",
    author="Tom Hosking",
    author_email="code@tomho.sk",
    description="A Seq2Seq framework for PyTorch",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tomhosking/torchseq",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires='>=3.6',
    entry_points = {
        'console_scripts': ['torchseq=torchseq.main:main'],
    },
    install_requires = [
        'tensorboard==2.9.0',
        'torch==1.12.0',
        'tqdm>=4.62',
        'scipy>=1.5',
        'nltk>=3.6.7',
        'transformers==4.18.0',
        'tokenizers==0.12.1',
        'jsonlines>=2',
        'sacrebleu>=2.0',
        'py-rouge',
        'rouge-score',
        'wandb==0.12.21',
        'matplotlib',
        'opentsne',
        'sentencepiece==0.1.95',
        'protobuf<4',
        'pydantic==1.9.1'
        # 'pytorch-lightning==1.5.9'
    ],
)