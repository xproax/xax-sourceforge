define([
    "dijit/Tree",
    "dojo/_base/declare",
    "dojo/_base/array",
    "dojo/_base/Deferred",
    "dojo/_base/lang"
    ], function(Tree, declare, array, Deferred, lang) {

    var MyTree = declare("freeadmin.tree.Tree", [Tree], {
        _expandNode: function( node, recursive){
            if(node._expandNodeDeferred && !recursive){
                return node._expandNodeDeferred;    // dojo.Deferred
            }

            //item = node.item;
            //alert("doing ya");
            //if (item._loadObject && !node._loadObjectFunction) {
            //    node._loadObjectFunction = item._loadObject;
            //}

            return this.inherited(arguments);

        },
        expandAll: function() {
            // summary:
            //     Expand all nodes in the tree
            // returns:
            //     Deferred that fires when all nodes have expanded

            var _this = this;

            function expand(node) {
                _this._expandNode(node);

                var childBranches = array.filter(node.getChildren() || [], function(node) {
                    return node.isExpandable;
                });

                var def = new Deferred();
                defs = array.map(childBranches, expand);
            }
            return expand(this.rootNode);
        },
        collapseAll: function() {
            // summary:
            //     Expand all nodes in the tree
            // returns:
            //     Deferred that fires when all nodes have expanded

            var _this = this;

            function collapse(node) {
                // never collapse root node, otherwise hides whole tree !
                if ( _this.showRoot == false && node != _this.rootNode ) {
                 _this._collapseNode(node);
                }

                var childBranches = array.filter(node.getChildren() || [], function(node) {
                    return node.isExpandable;
                });

                var def = new Deferred();
                defs = array.map(childBranches, collapse);
            }
            return collapse(this.rootNode);
        },
        reload: function () {

            this.model.store.close();
            path = this.get('path');

            if (this.rootNode) {
                this.rootNode.destroyRecursive();
            }

            this.rootNode.state = "UNCHECKED";

            storeTarget = this.model.store.target;
            for (var idx in dojox.rpc.Rest._index) {
                if (idx.match("^" + storeTarget)) {
                    delete dojox.rpc.Rest._index[idx];
                }
            }

            this.model.constructor(this.model);

            this.postMixInProperties();
            this._load();
            if(path && path.length > 0) {
                this.set('path', path).then(
                        lang.hitch(this, function() {
                            this.focusNode(this.get('selectedNode'));
                        }
                ));
            }

        }
    });
    return MyTree;

});
