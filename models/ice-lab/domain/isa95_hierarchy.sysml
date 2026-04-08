package ISA95EquipmentHierarchy {
    doc /* Abstract ISA-95 / IEC 62264 equipment hierarchy base types.
         * Defines the six standard levels used to structure manufacturing
         * facilities from enterprise down to individual production equipment.
         *
         * Reference: IEC 62264-1 (ISA-95 Part 1), Section 5 — Equipment Hierarchy.
         */
    part def Enterprise {
        doc /* ISA-95 Level 4: The organization or business entity
             * responsible for production across multiple sites.
             */
        abstract part sites : Site[*];
    }
    part def Site {
        doc /* ISA-95 Level 3: A geographically distinct facility
             * containing one or more operational areas.
             */
        abstract part areas : Area[*];
    }
    part def Area {
        doc /* ISA-95 Level 2: A logical or physical zone within a site,
             * grouping related production lines or processes.
             */
        abstract part production_lines : ProductionLine[*];
    }
    part def ProductionLine {
        doc /* ISA-95 Level 1: An ordered arrangement of work cells
             * that together produce a product or product family.
             */
        abstract part work_cells : WorkCell[*];
    }
    part def WorkCell {
        doc /* ISA-95 Level 0 (upper): A functional grouping of
             * production equipment that performs a specific
             * manufacturing step.
             */
        abstract part equipment : ProductionEquipment[*];
    }
    part def ProductionEquipment {
        doc /* ISA-95 Level 0 (lower): An individual machine, robot,
             * sensor, or actuator — the smallest independently
             * addressable unit of production equipment.
             */
    }
}
