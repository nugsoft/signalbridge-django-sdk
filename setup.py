from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="signalbridge-django-sdk",
    version="1.0.0",
    author="Asaba William",
    author_email="asabawilliam@gmail.com",
    description="Django SDK for SignalBridge SMS Gateway - Send SMS through multiple vendors with unified API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nugsoft/signalbridge-django-sdk",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Framework :: Django",
        "Framework :: Django :: 3.2",
        "Framework :: Django :: 4.0",
        "Framework :: Django :: 4.1",
        "Framework :: Django :: 4.2",
        "Framework :: Django :: 5.0",
    ],
    python_requires=">=3.8",
    install_requires=[
        "Django>=3.2",
        "requests>=2.25.0",
    ],
    include_package_data=True,
    zip_safe=False,
)
