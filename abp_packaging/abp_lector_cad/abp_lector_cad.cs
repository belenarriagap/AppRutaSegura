using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using ACadSharp;
using ACadSharp.Entities;
using ACadSharp.IO;
using CSMath;

static class abpLectorCad
{
    struct abpBox { public double abp_X0, abp_Y0, abp_X1, abp_Y1; }

    static int Main(string[] abp_args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        if (abp_args.Length < 2)
        {
            Console.Error.WriteLine("uso: lector_cad --lista plano.dwg | plano.dwg carpeta [laminas] | --dwg plano.dxf plano.dwg");
            return 2;
        }
        try
        {
            if (abp_args[0] == "--lista") abp_List(abp_args[1]);
            else if (abp_args[0] == "--dwg") abp_ToDwg(abp_args[1], abp_args[2]);
            else abp_Run(abp_args[0], abp_args[1], abp_args.Skip(2).ToList());
            return 0;
        }
        catch (Exception abp_e) { Console.Error.WriteLine(abp_e.GetType().Name + ": " + abp_e.Message); return 1; }
    }

    static void abp_List(string abp_source)
    {
        CadDocument abp_doc = DwgReader.Read(abp_source);
        foreach (var abp_layout in abp_Layouts(abp_doc)) Console.WriteLine("lamina\t" + abp_layout.Name);
    }

    static List<ACadSharp.Objects.Layout> abp_Layouts(CadDocument abp_doc)
    {
        return abp_doc.Layouts.Where(abp_l => abp_l.IsPaperSpace && abp_Windows(abp_l.AssociatedBlock).Count > 0).OrderBy(abp_l => abp_l.TabOrder).ToList();
    }

    static void abp_ToDwg(string abp_source, string abp_target)
    {
        CadDocument abp_doc = DxfReader.Read(abp_source);
        abp_doc.Header.Version = ACadVersion.AC1032;
        using (var abp_writer = new DwgWriter(abp_target, abp_doc)) abp_writer.Write();
    }

    static void abp_Run(string abp_source, string abp_folder, List<string> abp_names)
    {
        CadDocument abp_doc = DwgReader.Read(abp_source);
        Console.WriteLine("leido");
        abp_FlatGradients(abp_doc);
        var abp_entities = abp_Sorted(abp_doc.ModelSpace);
        foreach (var abp_block in abp_doc.BlockRecords.ToList())
            if (abp_block != abp_doc.ModelSpace && abp_block.SortEntitiesTable != null) abp_Fill(abp_block, abp_Sorted(abp_block));
        var abp_boxes = new Dictionary<Entity, abpBox>();
        foreach (Entity abp_e in abp_entities)
        {
            abpBox abp_b;
            if (abp_Bounds(abp_e, out abp_b)) abp_boxes[abp_e] = abp_b;
        }
        var abp_layouts = abp_Layouts(abp_doc).Where(abp_l => abp_names.Count == 0 || abp_names.Contains(abp_l.Name)).ToList();
        int abp_number = 0;
        foreach (var abp_layout in abp_layouts)
        {
            var abp_windows = abp_Windows(abp_layout.AssociatedBlock);
            var abp_kept = new List<Entity>();
            foreach (Entity abp_e in abp_entities)
            {
                abpBox abp_b;
                bool abp_known = abp_boxes.TryGetValue(abp_e, out abp_b);
                if (!abp_known || abp_windows.Any(abp_w => abp_b.abp_X1 >= abp_w.abp_X0 && abp_b.abp_X0 <= abp_w.abp_X1 && abp_b.abp_Y1 >= abp_w.abp_Y0 && abp_b.abp_Y0 <= abp_w.abp_Y1)) abp_kept.Add(abp_e);
            }
            abp_Fill(abp_doc.ModelSpace, abp_kept);
            abp_number++;
            var abp_emptied = abp_EmptyUnused(abp_doc, abp_layout.AssociatedBlock);
            abp_Save(abp_doc, Path.Combine(abp_folder, abp_number + ".dxf"));
            foreach (var abp_pair in abp_emptied) abp_Fill(abp_pair.Key, abp_pair.Value);
            Console.WriteLine("lamina\t" + abp_number + ".dxf\t" + abp_layout.Name + "\t" + abp_kept.Count);
        }
        if (abp_number == 0 && abp_names.All(abp_n => abp_n == "Model"))
        {
            abp_Save(abp_doc, Path.Combine(abp_folder, "1.dxf"));
            Console.WriteLine("lamina\t1.dxf\tModel\t" + abp_entities.Count);
        }
    }

    static void abp_FlatGradients(CadDocument abp_doc)
    {
        foreach (var abp_block in abp_doc.BlockRecords)
            foreach (Hatch abp_h in abp_block.Entities.OfType<Hatch>())
            {
                var abp_gradient = abp_h.GradientColor;
                if (abp_gradient == null || !abp_gradient.Enabled || abp_gradient.Colors.Count == 0) continue;
                int abp_r = 0, abp_g = 0, abp_b = 0, abp_n = abp_gradient.Colors.Count;
                foreach (var abp_c in abp_gradient.Colors) { abp_r += abp_c.Color.R; abp_g += abp_c.Color.G; abp_b += abp_c.Color.B; }
                abp_h.Color = new Color((byte)(abp_r / abp_n), (byte)(abp_g / abp_n), (byte)(abp_b / abp_n));
                abp_gradient.Enabled = false;
                abp_h.IsSolid = true;
                abp_h.Pattern = HatchPattern.Solid;
            }
    }

    static List<Entity> abp_Sorted(ACadSharp.Tables.BlockRecord abp_block)
    {
        var abp_list = abp_block.Entities.ToList();
        var abp_table = abp_block.SortEntitiesTable;
        if (abp_table == null) return abp_list;
        var abp_order = new Dictionary<Entity, ulong>();
        foreach (var abp_sorter in abp_table) if (abp_sorter.Entity != null) abp_order[abp_sorter.Entity] = abp_sorter.SortHandle;
        if (abp_order.Count == 0) return abp_list;
        ulong abp_h;
        return abp_list.OrderBy(abp_e => abp_order.TryGetValue(abp_e, out abp_h) ? abp_h : abp_e.Handle).ToList();
    }

    static void abp_Fill(ACadSharp.Tables.BlockRecord abp_block, IEnumerable<Entity> abp_entities)
    {
        abp_block.Entities.Clear();
        foreach (Entity abp_e in abp_entities) abp_block.Entities.Add(abp_e);
    }

    static Dictionary<ACadSharp.Tables.BlockRecord, List<Entity>> abp_EmptyUnused(CadDocument abp_doc, ACadSharp.Tables.BlockRecord abp_paper)
    {
        var abp_used = new HashSet<ACadSharp.Tables.BlockRecord>();
        var abp_pending = new Stack<ACadSharp.Tables.BlockRecord>();
        abp_pending.Push(abp_doc.ModelSpace);
        abp_pending.Push(abp_paper);
        while (abp_pending.Count > 0)
        {
            var abp_block = abp_pending.Pop();
            if (abp_block == null || !abp_used.Add(abp_block)) continue;
            foreach (Entity abp_e in abp_block.Entities)
            {
                var abp_insert = abp_e as Insert;
                if (abp_insert != null) abp_pending.Push(abp_insert.Block);
                var abp_dimension = abp_e as Dimension;
                if (abp_dimension != null) abp_pending.Push(abp_dimension.Block);
                var abp_leader = abp_e as MultiLeader;
                if (abp_leader != null) abp_pending.Push(abp_leader.BlockContent as ACadSharp.Tables.BlockRecord);
            }
        }
        foreach (var abp_style in abp_doc.DimensionStyles) abp_used.Add(abp_style.DimArrow1);
        var abp_emptied = new Dictionary<ACadSharp.Tables.BlockRecord, List<Entity>>();
        foreach (var abp_block in abp_doc.BlockRecords.Where(abp_b => !abp_used.Contains(abp_b) && abp_b.Entities.Count() > 40).ToList())
        {
            abp_emptied[abp_block] = abp_block.Entities.ToList();
            abp_block.Entities.Clear();
        }
        return abp_emptied;
    }

    static void abp_Save(CadDocument abp_doc, string abp_path)
    {
        using (var abp_writer = new DxfWriter(abp_path, abp_doc, false)) abp_writer.Write();
    }

    static List<abpBox> abp_Windows(ACadSharp.Tables.BlockRecord abp_block)
    {
        var abp_found = new List<abpBox>();
        foreach (Entity abp_e in abp_block.Entities)
        {
            var abp_v = abp_e as Viewport;
            if (abp_v == null || abp_v.Id == 1 || abp_v.ViewHeight <= 0 || abp_v.Height <= 0) continue;
            double abp_h = abp_v.ViewHeight, abp_w = abp_h * abp_v.Width / abp_v.Height;
            double abp_r = Math.Abs(abp_v.TwistAngle) > 1e-6 ? Math.Sqrt(abp_w * abp_w + abp_h * abp_h) : 0;
            double abp_cx = abp_v.ViewCenter.X + abp_v.ViewTarget.X, abp_cy = abp_v.ViewCenter.Y + abp_v.ViewTarget.Y;
            double abp_hw = Math.Max(abp_w, abp_r) / 2, abp_hh = Math.Max(abp_h, abp_r) / 2;
            abp_found.Add(new abpBox { abp_X0 = abp_cx - abp_hw, abp_Y0 = abp_cy - abp_hh, abp_X1 = abp_cx + abp_hw, abp_Y1 = abp_cy + abp_hh });
        }
        return abp_found;
    }

    static bool abp_Bounds(Entity abp_e, out abpBox abp_box)
    {
        abp_box = new abpBox();
        var abp_line = abp_e as Line;
        if (abp_line != null)
        {
            abp_box.abp_X0 = Math.Min(abp_line.StartPoint.X, abp_line.EndPoint.X); abp_box.abp_X1 = Math.Max(abp_line.StartPoint.X, abp_line.EndPoint.X);
            abp_box.abp_Y0 = Math.Min(abp_line.StartPoint.Y, abp_line.EndPoint.Y); abp_box.abp_Y1 = Math.Max(abp_line.StartPoint.Y, abp_line.EndPoint.Y);
            return true;
        }
        var abp_insert = abp_e as Insert;
        if (abp_insert != null && abp_insert.Attributes.Count() > 0) return false;
        var abp_text = abp_e as TextEntity;
        if (abp_text != null) return abp_Around(abp_text.InsertPoint, abp_text.Height * Math.Max(2, (abp_text.Value ?? "").Length), out abp_box);
        var abp_mtext = abp_e as MText;
        if (abp_mtext != null) return abp_Around(abp_mtext.InsertPoint, abp_mtext.Height * Math.Max(4, (abp_mtext.Value ?? "").Length), out abp_box);
        try
        {
            BoundingBox abp_b = abp_e.GetBoundingBox();
            if (abp_b.Extent != BoundingBoxExtent.Finite) return false;
            abp_box.abp_X0 = abp_b.Min.X; abp_box.abp_Y0 = abp_b.Min.Y; abp_box.abp_X1 = abp_b.Max.X; abp_box.abp_Y1 = abp_b.Max.Y;
            return !(double.IsNaN(abp_box.abp_X0) || double.IsInfinity(abp_box.abp_X0) || double.IsNaN(abp_box.abp_X1));
        }
        catch { return false; }
    }

    static bool abp_Around(XYZ abp_p, double abp_reach, out abpBox abp_box)
    {
        abp_box = new abpBox { abp_X0 = abp_p.X - abp_reach, abp_Y0 = abp_p.Y - abp_reach, abp_X1 = abp_p.X + abp_reach, abp_Y1 = abp_p.Y + abp_reach };
        return true;
    }
}
