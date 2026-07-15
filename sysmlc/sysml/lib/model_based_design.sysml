// Subset of the ODE4HERA "Model-Based Design" library (v2.0), bundled so
// sysmlc models can declare imported FMUs in the ODE4HERA idiom without
// installing the full library:
//
//   #mbd_component part def X {
//       @ExecutableModelMetadata { :>> externalModelLink = "x.fmu"; }
//       port p;
//       #fmu_behavior perform action dynamics {
//           @BehavioralModelMetadata { :>> maxTimeStep = 0.1; }
//           out y : ScalarValues::Real;   // FMU output variable
//           in  u : ScalarValues::Real;   // FMU input variable
//           #mbd_parameter attribute g : ScalarValues::Real = -9.81;
//       }
//   }
//
// Source: https://www.ode4hera.eu/ (ode4hera-simulation-and-analysis,
// ModelBasedDesign.sysml). Only the definitions the frostifier extraction
// reads are retained; a model importing the full ODE4HERA library instead
// works identically (matching is by name).
//
// MIT License
// Copyright: (c) 2026, The Contributors to the ODE4HERA SysML v2 Libraries.
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

library package ModelBasedDesign {
    doc /* Meta-information and semantic metadata for executable
         * behavioral models (subset; see the file header). */

    public import MBDSemanticMetadata::*;

    metadata def ExecutableModelMetadata {
        doc /* Meta-info for executable models; `externalModelLink` names
             * the executable artifact (for frostifier: the .fmu archive,
             * relative to the declaring .sysml file). */
        attribute authoringTool : ScalarValues::String [0..1];
        attribute domain : ScalarValues::String [0..1];
        attribute externalModelLink : ScalarValues::String [0..1];
        :> annotatedElement : SysML::PartDefinition;
        :> annotatedElement : SysML::PartUsage;
        :> annotatedElement : SysML::PortDefinition;
        :> annotatedElement : SysML::PortUsage;
    }

    metadata def BehavioralModelMetadata :> ExecutableModelMetadata {
        doc /* Behavioral-model specifics; frostifier reads `maxTimeStep`
             * as the co-simulation communication interval in seconds. */
        attribute maxTimeStep : ScalarValues::Real [0..1];
        attribute minTimeStep : ScalarValues::Real [0..1];
        :> annotatedElement : SysML::ActionDefinition;
        :> annotatedElement : SysML::ActionUsage;
    }

    abstract part def MBDContainer {
        doc /* Reusable modular unit of simulation structure. */
        abstract part components : SimulationComponent[0..*] :> subparts;
        abstract ref action behaviors : MBDBehavior[0..*] :> performedActions;
    }

    part def SimulationComponent :> MBDContainer;

    action def MBDBehavior {
        doc /* Base definition of an executable behavioral model. */
    }

    action def FMUBehavior :> MBDBehavior {
        doc /* MBD behavior realized by an FMU (FMI standard). */
    }
    abstract ref action fmuBehaviors : FMUBehavior[*];

    alias MBDParameter for Base::DataValue;
    attribute mbdParameters : MBDParameter[*];

    package MBDSemanticMetadata {
        doc /* Domain-specific semantic metadata (`#` annotations). */

        metadata def <mbd_component> SimulationComponentDSM :> Metaobjects::SemanticMetadata {
            doc /* #mbd_component declares a simulation component model. */
            :> annotatedElement : SysML::PartDefinition;
            :> annotatedElement : SysML::PartUsage;
            :>> baseType = MBDContainer::components meta SysML::PartUsage;
        }
        metadata def <fmu_behavior> FMUBehaviorDSM :> Metaobjects::SemanticMetadata {
            doc /* #fmu_behavior declares an FMU behavior; its in/out
                 * parameters are the FMU's input/output variables. */
            :> annotatedElement : SysML::ActionUsage;
            :>> baseType = fmuBehaviors meta SysML::ActionUsage;
        }
        metadata def <mbd_parameter> MBDParameterDSM :> Metaobjects::SemanticMetadata {
            doc /* #mbd_parameter declares an independent parameter (a
                 * constant provided by the environment; for frostifier:
                 * an FMU startup value). */
            :> annotatedElement : SysML::AttributeUsage;
            :>> baseType = mbdParameters meta SysML::AttributeUsage;
        }
    }
}
