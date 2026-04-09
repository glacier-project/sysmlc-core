package OpcUaBinding {
    doc /* Metadata definitions for binding SysMLv2 model elements
         * to their OPC-UA address space identities.
         */

    private import ScalarValues::*;

    metadata def OpcUaMethod {
        doc /* Binds an action def to its OPC-UA method node. */
        attribute nodeId : String;
        attribute parentNodeId : String;
    }

    metadata def OpcUaVariable {
        doc /* Binds an attribute to its OPC-UA monitored variable node. */
        attribute nodeId : String;
    }

    metadata def OpcUaConnection {
        doc /* Binds an equipment usage to its OPC-UA server endpoint. */
        attribute endpoint : String;
    }
}
