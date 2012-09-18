ReCMS is a Content Management System based on the excellent Pyramid framework that uses MongoDB for persistence and ElasticSearch, you know, for search.

It's a work in progress (definitely not for production use yet), but already supports:

* hierarchical folders of content (an example Article type is included; new types are easy to define and register)
* CRUD and folder operations (cut, copy, paste, rename, re-order), all with history logging
* add/edit forms use Deform; content types use Colander to define schemas
* basic publishing workflow
* a trash folder for deleted content, with support for restore and copy
* edit history compare and revert
* user management, groups and local roles
* and of course, full text search

Installation
============

Note that I've only run ReCMS on Linux. I'm assuming that the instructions below would work just as well under OS X, but can't say for sure.

Prerequisites
-------------

1. Python 2.6 or later is required for Pyramid.
   Also install virtualenv.

   Refer to the Pyramid docs for instructions: http://docs.pylonsproject.org/projects/pyramid/en/1.3-branch/narr/install.html

2. MongoDB

   If you don't already have a MongoDB server, install the latest production release from http://www.mongodb.org/downloads (I'm currently (2012-06-23) using 2.0.6.)
   
   If you just want to quickly try out ReCMS, here's a recipe for running a MongoDB server in the foreground under your non-root user account:

        wget http://fastdl.mongodb.org/linux/mongodb-linux-x86_64-2.0.6.tgz
        tar xfz mongodb-linux-x86_64-2.0.6.tgz
        ln -s mongodb-linux-x86_64-2.0.6 mongodb
        cd mongodb
        mkdir -p data
        bin/mongod --dbpath=data --rest

3. ElasticSearch

   If you don't already have an ElasticSearch server, install the latest production release from http://www.elasticsearch.org/download/ (I'm currently using 0.19.4.)
   
   If you just want to quickly try out ReCMS, here's a recipe for running an ElasticSearch server in the foreground under your non-root user account:

        wget https://github.com/downloads/elasticsearch/elasticsearch/elasticsearch-0.19.4.tar.gz
        tar xfz elasticsearch-0.19.4.tar.gz
        ln -s elasticsearch-0.19.4 elasticsearch
        cd elasticsearch
        bin/plugin -install elasticsearch/elasticsearch-transport-thrift/1.2.0
        bin/elasticsearch -f
   
Setup Instructions
------------------

1. Create and activate a Python virtual environment:

        virtualenv cms_env
        cd cms_env
        source bin/activate

2. Either move or symlink the recms repository into the cms_env directory:

        mv PATH_TO/recms .
        ### or ###
        ln -s PATH_TO/recms recms

   Then cd into it:

        cd recms

3. Install (in development mode):

        python setup.py develop

4. Review the config file (development.ini) and change any settings you like.
   Most of the config is standard Pyramid stuff.
   Here are some of the ReCMS custom settings you may want to change (but you can probably leave them at the defaults if you just want to do a quick test drive and are running MongoDB and ElasticSearch with the default ports on localhost, as would be the case if you followed the recipes under the Prerequisites section earlier):
   * db_uri
   * db_name
   * es_uri
   * es_name
   * default_timezone
   * mail.host
   * mail.port


5. Create an initial superuser account (with the username and password of your choice) using pshell:

        pshell development.ini#main
        root.add_super_user('USERNAME', 'PASSWORD')
   
   Ctrl-D to exit pshell

6. Run the application:

        pserve development.ini --reload

7. The moment of truth... in your browser hit http://127.0.0.1:6543/
   You should see an empty site (exciting, I know).
   Click the Login link in the top bar and log in with the username and password you setup in the pshell, then start exploring the menus.


