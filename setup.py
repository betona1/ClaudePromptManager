from setuptools import setup, find_packages

setup(
    name="cpm",
    version="2.0.0",
    description="CPM - Claude Prompt Manager: CLI + Web prompt management system",
    author="김준용",
    author_email="netkjy@gmail.com",
    packages=find_packages(),
    py_modules=["cpm", "cpm_cli"],
    install_requires=[
        "django>=4.2",
        "djangorestframework>=3.14",
        "django-allauth>=0.61.0",
        "rich>=13.0.0",
        "redis>=5.0.0",
        "whitenoise>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "cpm=cpm:main",
            "cpm2=cpm_cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
