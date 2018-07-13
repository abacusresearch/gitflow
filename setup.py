import os

from setuptools import setup

from gitflow import const


def load_requirements(file):
    with open(file) as dependency_file:
        return list(filter(lambda line: len(line),
                           [line.split('#')[0].strip() for line in dependency_file.readlines()]
                           ))


def determine_module_names(base_dir):
    return [dirpath.replace(os.sep, '.') for dirpath, dirnames, filenames in os.walk(base_dir)
            if '__init__.py' in filenames]


setup(name='gitflow',
      version=const.VERSION,
      description='Git Flow',
      url='http://www.abacus.ch',
      author='Samuel Oggier',
      author_email='samuel.oggier@gmail.com',
      license='MIT',
      python_requires=">=3.0",
      packages=determine_module_names('gitflow'),
      package_data={'gitflow': ['config.ini']},
      install_requires=load_requirements('requirements.txt'),
      tests_require=load_requirements('test_requirements.txt'),
      zip_safe=False,
      entry_points={
          'console_scripts': [
              'git-flow=gitflow.__main__:main',
          ],
      },
      )
