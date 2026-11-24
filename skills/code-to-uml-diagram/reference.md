# Reference

主流程见 [SKILL.md](SKILL.md)。

## 样例

类图：

```mermaid
classDiagram
    class Toolkit {
        +list_tools()
        +execute_tool(name, input)
        +add_tool(tool)
    }
    class LiberoToolkit {
        +init_primitives()
        +solved()
    }
    Toolkit <|-- LiberoToolkit
    Toolkit *-- _Scheduler
    Toolkit --> MemoryManager
    Toolkit ..> CommonTools : 构造并注册
    CommonTools --> MemoryManager
    LiberoToolkit *-- LiberoPrimitives
```

- `Toolkit.__init__` 自己创建 `_Scheduler`；`MemoryManager` 由调用方传入，`CommonTools` 拿到的是同一个实例。

时序图（一次 `pi0_pick` 工具调用；帧按 env step 攒、按工具调用切）：

```mermaid
sequenceDiagram
    participant P as Planner
    participant T as LiberoToolkit
    participant Pr as LiberoPrimitives
    participant E as LiberoEnvClient

    Note over T,Pr: init_primitives：reset → start_recording → 记 cursor
    P->>T: pi0_pick(prompt)
    T->>Pr: begin_primitive
    loop 每个 chunk
        Pr->>E: chunk_step(actions, return_all_frames=True)
        E-->>Pr: 每一步的 obs
        Pr->>Pr: record_frame
    end
    Pr-->>T: ToolResult
    T->>T: dump_state
    opt dashboard 开
        T->>Pr: frame_slice(cursor)
    end
    T-->>P: state + 图像
    Note over T,Pr: close：stop_recording → episode.mp4
```

- 帧缓冲在 `LiberoPrimitives` 里，因为只有它经过每个 env step；`LiberoToolkit` 只看得到调用的首尾（推断）。
