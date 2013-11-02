#!/usr/bin/env python

"""
Compiles the Doorstop document hierarchy.
"""

import os
import sys
import shutil
import subprocess
import logging
from itertools import chain

from doorstop.common import DoorstopError
from doorstop.core.document import Document
from doorstop.core.item import Item
from doorstop.core import vcs


class Node(object):
    """
    A bidirectional tree structure to store the document heirarchy.

    Although requirements link "upwards", bidirectionality simplifies
    document processing and validation.
    """

    def __init__(self, document, parent=None):
        self.document = document
        self.parent = parent
        self.children = []

    def __repr__(self):
        return "<Node {}>".format(self)

    def __str__(self):
        children = ", ".join(str(c) for c in self.children)
        if children:
            return "{} <- [ {} ]".format(self.document, children)
        else:
            return "{}".format(self.document)

    def __len__(self):
        return 1 + sum(len(child) for child in self.children)

    def __getitem__(self, key):
        raise IndexError("{} cannot be indexed by key".format(self.__class__))

    def __iter__(self):
        yield self.document
        for document in chain(*(iter(c) for c in self.children)):
            yield document

    @staticmethod
    def from_list(docs):
        """Get a new tree from the list of Documents.

        @param root: path to root of the project
        @param documents: list of Documents

        @return: tree built from Nodes

        @raise DoorstopError: when the tree cannot be built
        """
        unplaced = list(docs)
        for doc in list(unplaced):
            if doc.parent is None:
                logging.debug("added root of tree: {}".format(doc))
                tree = Node(doc)
                logging.info("root of tree: {}".format(doc))
                unplaced.remove(doc)
                break
        else:
            raise DoorstopError("no root document")

        while unplaced:
            count = len(unplaced)
            for doc in list(unplaced):
                try:
                    tree.place(doc)
                except DoorstopError as error:
                    logging.debug(error)
                else:
                    logging.info("added to tree: {}".format(doc))
                    unplaced.remove(doc)

            if len(unplaced) == count:  # no more documents could be placed
                logging.debug("unplaced documents: {}".format(unplaced))
                msg = "unplaced document: {}".format(unplaced[0])
                raise DoorstopError(msg)

        return tree

    def place(self, doc):
        """Attempt to place the Document in the current tree.

        @param doc: Document to add

        @raise DoorstopError: if the Document cannot yet be placed
        """
        logging.debug("trying to add '{}'...".format(doc))
        if doc.parent == self.document.prefix:
            node = Node(doc, self)
            self.children.append(node)
        else:
            for child in self.children:
                try:
                    child.place(doc)
                except DoorstopError:
                    pass  # the error is raised later
                else:
                    break
            else:
                msg = "no parent for: {}".format(doc)
                raise DoorstopError(msg)

    def check(self):
        """Confirm the document hiearchy is valid.

        @return: indication that hiearchy is valid

        @raise DoorstopError: on issue
        """
        logging.info("checking tree...")
        for document in self:
            document.check()
        return True

    def new(self, path, prefix, parent=None, digits=None):
        """Create a new document and add it to the tree.

        @param path: directory path for the new document
        @param prefix: document's prefix
        @param parent: parent document's prefix
        @param digits: number of digits for the document's numbers

        @return: newly created and placed Document

        @raise DoorstopError: if the document cannot be created
        """
        document = Document.new(path, self.document.root, prefix,
                                parent=parent, digits=digits)
        try:
            self.place(document)
        except DoorstopError:
            msg = "deleting unplaced directory {}...".format(document.path)
            logging.debug(msg)
            if os.path.exists(document.path):
                shutil.rmtree(document.path)
            raise
        return document

    def add(self, prefix):
        """Add a new item to an existing document.

        @param prefix: document's prefix

        @return: newly created Item

        @raise DoorstopError: if the item cannot be created
        """
        for document in self:
            if document.prefix.lower() == prefix.lower():
                return document.add()

        raise DoorstopError("no matching prefix: {}".format(prefix))

    # TODO: refactor
    def link(self, cid, pid):
        """Add a new item to an existing document.

        @param cid: child item's ID
        @param pid: parent item's ID

        @return: (child, parent) item pair

        @raise DoorstopError: if the link cannot be created
        """
        # Find child item
        child = None
        prefix, number = Item.split_id(cid)
        for document in self:
            if document.prefix.lower() == prefix.lower():
                for item in document:
                    if item.number == number:
                        child = item
                        break
                if child is None:
                    logging.warning("no matching child number: {}".format(number))
                else:
                    break
        if child is None:
            logging.warning("no matching child prefix: {}".format(prefix))
            raise DoorstopError("no matching child ID: {}".format(cid))

        # Find parent item
        parent = None
        prefix, number = Item.split_id(pid)
        for document in self:
            if document.prefix.lower() == prefix.lower():
                for item in document:
                    if item.number == number:
                        parent = item
                        break
                if parent is None:
                    logging.warning("no matching parent number: {}".format(number))
                else:
                    break
        if parent is None:
            logging.warning("no matching parent prefix: {}".format(prefix))
            raise DoorstopError("no matching parent ID: {}".format(cid))

        # Add link
        child.add_link(parent.id)
        return child, parent

    def edit(self, identifier, launch=False):
        """Open an item for editing.

        @param identifier: ID of item to edit
        @param launch: open the default text editor

        @raise DoorstopError: if the item cannot be found
        """
        logging.debug("looking for {}...".format(identifier))
        prefix, number = Item.split_id(identifier)

        for document in self:
            if document.prefix.lower() == prefix.lower():
                for item in document:
                    if item.number == number:
                        if launch:
                            _open(item.path)
                        return
                logging.warning("no matching number: {}".format(number))
                break
        else:
            logging.warning("no matching prefix: {}".format(prefix))

        raise DoorstopError("no matching ID: {}".format(identifier))


def _open(path):  # pragma: no cover, integration test
    """Open the text file using the default editor."""
    if sys.platform.startswith('darwin'):
        args = ['open', path]
        logging.debug("$ {}".format(' '.join(args)))
        subprocess.call(args)
    elif os.name == 'nt':
        logging.debug("$ (start) {}".format(path))
        os.startfile(path)  # pylint: disable=E1101
    elif os.name == 'posix':
        args = ['xdg-open', path]
        logging.debug("$ {}".format(' '.join(args)))
        subprocess.call(args)


def build(cwd):
    """Build a document heirachy from the current root directory.

    @param cwd: current working directory

    @return: tree built from Nodes

    @raise DoorstopError: when the tree cannot be built
    """
    documents = []

    # Find the root of the working copy
    root = vcs.find_root(cwd)

    # Find all documents in the working copy
    logging.info("looking for documents in {}...".format(root))
    _add_document_from_path(root, root, documents)
    for dirpath, dirnames, _ in os.walk(root):
        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            _add_document_from_path(path, root, documents)

    # Build the document tree
    if not documents:
        logging.warning("no documents found")
    logging.info("building document tree...")
    tree = Node.from_list(documents)
    logging.info("final tree: {}".format(tree))
    return tree


def _add_document_from_path(path, root, documents):
    """Attempt to create and append a document from the specified path.

    @param path: path to a potential document
    @param root: path to root of working copy
    @param documents: list of documents to append results
    """
    try:
        document = Document(path, root)
    except DoorstopError:
        pass  # no document in directory
    else:
        if document.skip:
            logging.debug("skipping document: {}".format(document))
        else:
            logging.info("found document: {}".format(document))
            documents.append(document)
