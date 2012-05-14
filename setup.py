import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.txt')).read()
CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()

requires = [
    'pyramid',
    'pyramid_debugtoolbar',
    'pyramid_zcml',
    'pyramid_mailer',
    'repoze.workflow',
    'pymongo',
    'pyes',
    'pytz',
    'thrift',
    'deform',
    'WebTest',
    'PIL',
]

setup(name='cms',
      version='0.1',
      description='cms',
      long_description=README + '\n\n' +  CHANGES,
      classifiers=[
        "Programming Language :: Python",
        "Framework :: Pylons",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        ],
      author='Sam Brauer',
      author_email='sam.brauer@gmail.com',
      url='',
      keywords='web pyramid pylons',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires=requires,
      tests_require=requires,
      test_suite="cms",
      entry_points = """\
      [paste.app_factory]
      main = cms:main
      """,
      paster_plugins=['pyramid'],
      )

